"""Session durability across deploys: the write-behind workspace flusher.

The incident these pin: agent workspace writes were batched into ONE
fire-and-forget turn-end sync, so an instance drain mid-turn (deploy) lost
the entire turn's files. The flusher makes writes durable continuously — a
mark at every tool boundary triggers a debounced incremental sync — and the
provider refuses to commit a manifest for a deleted (missing-scratch)
session, so a background flush racing a delete can't resurrect it.

Plan: plans/session-durability-mid-turn-flush.md (siliconcrew-dev).
"""
import os
import shutil
import threading
import time

from src.platform_engines.workspace_flusher import WorkspaceFlusher
from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
)


class _RecordingProvider:
    """Fake provider: records sync calls; optional per-call failures/delay."""

    def __init__(self, fail_times: int = 0, delay: float = 0.0):
        self.synced = []
        self.fail_times = fail_times
        self.delay = delay
        self._lock = threading.Lock()

    def sync(self, session_id):
        if self.delay:
            time.sleep(self.delay)
        with self._lock:
            if self.fail_times > 0:
                self.fail_times -= 1
                raise RuntimeError("transient store error")
            self.synced.append(session_id)


class _NoSyncProvider:
    """Self-host shape: no ``sync`` attribute at all."""


def _flusher(provider, **kw):
    kw.setdefault("base_cooldown_sec", 0.05)
    kw.setdefault("retry_base_sec", 0.02)
    kw.setdefault("retry_max_sec", 0.1)
    return WorkspaceFlusher(provider_resolver=lambda: provider, **kw)


def _wait_for(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return pred()


def test_mark_dirty_flushes_promptly():
    """Leading edge: the first mark after idle syncs at once — the exposure
    window for a lone write is milliseconds, not a whole turn."""
    provider = _RecordingProvider()
    f = _flusher(provider)
    try:
        f.mark_dirty("s1")
        assert _wait_for(lambda: provider.synced == ["s1"])
    finally:
        f.close()


def test_burst_coalesces_but_last_write_is_covered():
    """N rapid marks inside the cooldown coalesce; the trailing sync runs
    AFTER the last mark so nothing is left behind."""
    provider = _RecordingProvider()
    f = _flusher(provider, base_cooldown_sec=0.1)
    try:
        for _ in range(20):
            f.mark_dirty("s1")
            time.sleep(0.002)
        assert f.flush_now("s1", timeout=5.0)
        n = len(provider.synced)
        assert 1 <= n <= 4, f"expected coalescing, got {n} syncs"
    finally:
        f.close()


def test_mark_during_in_flight_sync_triggers_trailing_sync():
    """A write that lands while a sync is running must be picked up by a
    follow-up sync (no lost update)."""
    provider = _RecordingProvider(delay=0.05)
    f = _flusher(provider)
    try:
        f.mark_dirty("s1")
        assert _wait_for(lambda: len(provider.synced) >= 1 or provider.delay == 0)
        f.mark_dirty("s1")  # likely lands mid-flight given the delay
        assert f.flush_now("s1", timeout=5.0)
        assert len(provider.synced) >= 2
    finally:
        f.close()


def test_flush_now_waits_and_reports():
    provider = _RecordingProvider(delay=0.05)
    f = _flusher(provider)
    try:
        f.mark_dirty("s1")
        assert f.flush_now("s1", timeout=5.0) is True
        assert provider.synced == ["s1"]
        # Clean session: immediate True, no extra sync.
        assert f.flush_now("s1", timeout=5.0) is True
        assert provider.synced == ["s1"]
    finally:
        f.close()


def test_flush_all_drains_every_dirty_session():
    provider = _RecordingProvider()
    f = _flusher(provider, base_cooldown_sec=60.0)  # cooldown can't help here
    try:
        f.mark_dirty("a")
        f.mark_dirty("b")
        f.mark_dirty("c")
        results = f.flush_all(timeout=5.0)
        assert set(provider.synced) >= {"a", "b", "c"}
        assert all(results.values()), results
    finally:
        f.close()


def test_failed_sync_retries_until_success():
    """A transient store error must never drop writes: session stays dirty
    and retries with backoff until the sync lands."""
    provider = _RecordingProvider(fail_times=2)
    f = _flusher(provider)
    try:
        f.mark_dirty("s1")
        assert _wait_for(lambda: provider.synced == ["s1"])
    finally:
        f.close()


def test_marks_do_not_defeat_retry_backoff():
    """Regression (fails pre-fix): during a store outage an active turn keeps
    marking; those marks must NOT pull the retry due earlier, or the flusher
    hammers the failing store every cooldown and the backoff never engages."""
    provider = _RecordingProvider(fail_times=1000)
    f = _flusher(provider, base_cooldown_sec=0.01,
                 retry_base_sec=10.0, retry_max_sec=10.0)
    try:
        f.mark_dirty("s1")
        # Let the first attempt fail; the retry is now ~10s out.
        assert _wait_for(lambda: provider.fail_times < 1000)
        attempts_after_first = 1000 - provider.fail_times
        # An active turn: rapid marks for a while.
        for _ in range(30):
            f.mark_dirty("s1")
            time.sleep(0.005)
        assert 1000 - provider.fail_times == attempts_after_first, (
            "ordinary marks pulled the retry due forward past the backoff"
        )
    finally:
        f.close()


def test_note_agent_frame_marks_only_tool_frames():
    provider = _RecordingProvider()
    f = _flusher(provider)
    try:
        f.note_agent_frame("s1", {"type": "text", "content": "hi"})
        f.note_agent_frame("s1", {"type": "ping"})
        f.note_agent_frame("s1", "not-a-dict")
        time.sleep(0.1)
        assert provider.synced == []
        f.note_agent_frame("s1", {"type": "tool_result", "tool_call_id": "t1"})
        assert _wait_for(lambda: provider.synced == ["s1"])
        f.note_agent_frame("s2", {"type": "tool_call", "tool": {}})
        assert _wait_for(lambda: "s2" in provider.synced)
    finally:
        f.close()


def test_no_sync_provider_is_a_safe_no_op():
    """Self-host: provider has no sync — every entry point is safe and the
    session drains clean (nothing to persist)."""
    f = _flusher(_NoSyncProvider())
    try:
        f.mark_dirty("s1")
        f.note_agent_frame("s1", {"type": "tool_result"})
        f.flush_soon("s1")
        assert f.flush_now("s1", timeout=5.0) is True
        assert f.flush_all(timeout=1.0) == {}  # already clean
    finally:
        f.close()


def test_discard_drops_dirty_state_and_stops_retries():
    provider = _RecordingProvider(fail_times=1000, delay=0.0)
    f = _flusher(provider, retry_base_sec=0.01, retry_max_sec=0.01)
    try:
        f.mark_dirty("s1")
        time.sleep(0.05)  # let at least one failing attempt happen
        f.discard("s1")
        time.sleep(0.05)
        before = provider.fail_times
        time.sleep(0.1)
        # No further attempts after discard settles (each attempt decrements).
        assert provider.fail_times == before
        assert provider.synced == []
    finally:
        f.close()


def test_idle_entries_are_pruned_so_state_stays_bounded():
    """A session that went clean and quiet (including a deleted session
    re-marked by a late frame) must not hold a _state entry forever."""
    provider = _RecordingProvider()
    f = _flusher(provider)
    f._idle_prune_sec = 0.01
    try:
        # A deleted-then-late-marked session: discard, then a stray mark.
        f.mark_dirty("dead")
        assert f.flush_now("dead", timeout=5.0)
        f.discard("dead")
        f.mark_dirty("dead")  # late frame after delete
        assert f.flush_now("dead", timeout=5.0)
        time.sleep(0.05)
        # Another session's sync runs the prune sweep.
        f.mark_dirty("live")
        assert f.flush_now("live", timeout=5.0)
        with f._cond:
            assert "dead" not in f._state, "idle entry survived the prune sweep"
    finally:
        f.close()


def test_delete_session_endpoint_discards_pending_flush(monkeypatch):
    """The DELETE route must drop the session's pending flush state (after a
    successful delete) so a retrying flush doesn't outlive the session."""
    import pytest
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api

    provider = _RecordingProvider(fail_times=1000)
    flusher = _flusher(provider, retry_base_sec=0.01, retry_max_sec=0.01)
    monkeypatch.setattr(api, "get_workspace_flusher", lambda: flusher)
    try:
        c = TestClient(api.app)
        sid = c.post("/api/sessions", json={"name": "flushdel"}).json()["id"]
        flusher.mark_dirty(sid)  # pending (and failing → retrying) flush
        time.sleep(0.03)
        assert c.delete(f"/api/sessions/{sid}").status_code == 200
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with flusher._cond:
                st = flusher._state.get(sid)
                if st is None or st["in_flight"] is False and not st["dirty"]:
                    break
            time.sleep(0.01)
        with flusher._cond:
            st = flusher._state.get(sid)
            assert st is None or (not st["dirty"] and not st["in_flight"]), (
                "DELETE left a dirty/retrying flush behind"
            )
    finally:
        flusher.close()


# --- the provider-side resurrection guard (Amendment A1) --------------------


def _cloud_provider(tmp_path):
    store = InMemoryObjectStore()
    provider = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    return store, provider


def test_sync_after_delete_does_not_resurrect_manifest(tmp_path):
    """Regression (fails pre-fix): a background flush racing a session delete
    must NOT re-commit an empty-but-adoptable manifest for the deleted id —
    delete_workspace purged the durable manifest on purpose (D7)."""
    store, provider = _cloud_provider(tmp_path)
    ws = provider.workspace_for("sess1")
    with open(os.path.join(ws, "top.v"), "w") as fh:
        fh.write("module top; endmodule\n")
    provider.sync("sess1")
    manifest_key = provider._manifest_key("sess1")
    assert store.get_file(manifest_key, str(tmp_path / "m1.json"))

    provider.delete_workspace("sess1")
    assert not store.get_file(manifest_key, str(tmp_path / "m2.json"))

    # The racing flush: scratch is gone → sync must be a no-op.
    provider.sync("sess1")
    assert not store.get_file(manifest_key, str(tmp_path / "m3.json")), (
        "sync() resurrected the manifest of a deleted session"
    )


def test_sync_of_empty_but_existing_scratch_still_commits(tmp_path):
    """The guard is about MISSING scratch only — a legitimately emptied
    workspace must still sync (deleting the last file propagates)."""
    store, provider = _cloud_provider(tmp_path)
    ws = provider.workspace_for("sess2")
    with open(os.path.join(ws, "a.v"), "w") as fh:
        fh.write("x")
    provider.sync("sess2")
    os.remove(os.path.join(ws, "a.v"))
    provider.sync("sess2")
    # Cold hydrate elsewhere sees the empty tree, not the stale file.
    shutil.rmtree(ws)
    os.remove(provider._marker_path("sess2"))
    os.remove(provider._index_path("sess2"))
    ws2 = provider.workspace_for("sess2")
    assert os.listdir(ws2) == []
