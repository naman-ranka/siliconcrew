"""Cross-instance status recovery must run the SAME past-ceiling reconcile.

Staging bug (invariant #5 violation): run synth_0009 (hosted) dispatched
18:09:39Z with timeout_sec 3600; its Cloud Run execution died at 19:11:46Z. A
DIFFERENT backend instance answered get_synthesis_status at ~19:12-19:15Z with
status "queued", synth "running", elapsed null, recovered_from_index true — a
dead run past its ceiling reading as alive.

Root cause: the reader's local (workspace-synced) run_meta was the dispatch-time
"queued" snapshot. The dispatching instance had pushed a durable "running"
milestone, but the reconciler's remote-meta adoption only took TERMINAL remote
metas, so the reader kept "queued" (status regressed backward) AND the death
verdict then granted it the queued double-grace (~2x timeout), so it wasn't
declared failed for ~2 hours. Fix: adopt a durable meta whenever it is strictly
more advanced (queued < running < terminal), never backward.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.platform_engines.workspace_provider import InMemoryObjectStore
from src.tools import synthesis_manager as sm
from src.utils.session_context import SessionContext, session_scope


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _age_files(root: str, seconds_ago: float) -> None:
    import time as _time

    ts = _time.time() - seconds_ago
    for r, _dirs, files in os.walk(root):
        for name in files:
            os.utime(os.path.join(r, name), (ts, ts))


@pytest.fixture
def durable_store():
    store = InMemoryObjectStore()
    sm.set_durable_run_store(store)
    try:
        yield store
    finally:
        sm.set_durable_run_store(None)


@pytest.fixture
def event_spy(monkeypatch):
    import src.utils.attempt_logger as attempt_logger

    calls = []

    def _record(workspace, session_id, source, tool, result, status="success", **kwargs):
        calls.append({"tool_call_id": kwargs.get("tool_call_id")})

    monkeypatch.setattr(attempt_logger, "log_tool_result", _record)
    return calls


def _push_remote(store, handle: str, meta: dict, tmp_path) -> None:
    src = tmp_path / f"remote_{handle.replace('/', '_')}.json"
    src.write_text(json.dumps(meta), encoding="utf-8")
    store.put_file(f"{handle}/meta/{sm.RUN_META_FILENAME}", str(src))


def _reader_with_queued_local(tmp_path, dispatched_ago: float, timeout_sec: int = 600):
    """A fresh reader instance whose local scratch holds only the dispatch-time
    'queued' snapshot (no created_at), with no live future in _JOBS."""
    ws = str(tmp_path / "instance_b")
    run_dir = os.path.join(ws, "synth_runs", "synth_0001")
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": "synth_0001",
            "status": "queued",
            "dispatched_at": _iso_ago(dispatched_ago),
            "timeout_sec": timeout_sec,
            "max_stage": "finish",
            "top_module": "counter",
            "platform": "sky130hd",
            "backend": "cloud_job",
        }),
    )
    _age_files(run_dir, dispatched_ago)  # idle since dispatch — liveness cold
    assert sm._job_key(ws, "synth_0001") not in sm._JOBS
    return ws, run_dir


def test_status_rank_is_monotonic():
    assert sm._status_rank("queued") < sm._status_rank("running")
    assert sm._status_rank("running") < sm._status_rank("completed")
    assert sm._status_rank("running") < sm._status_rank("failed")
    assert sm._status_rank(None) == sm._status_rank("queued")


def test_cross_instance_past_ceiling_queued_local_is_declared_failed(
    tmp_path, durable_store, event_spy
):
    session_id = "sess-x"
    # timeout 600: past the single ceiling (>720s) but NOT the old queued
    # double-grace (<1320s), so pre-fix it read as alive and post-fix it fails.
    ws, run_dir = _reader_with_queued_local(tmp_path, dispatched_ago=1000.0, timeout_sec=600)
    _push_remote(
        durable_store,
        f"{session_id}/synth_0001",
        {
            "run_id": "synth_0001",
            "status": "running",
            "dispatched_at": _iso_ago(1000.0),
            "created_at": _iso_ago(990.0),
            "timeout_sec": 600,
            "max_stage": "finish",
            "top_module": "counter",
            "platform": "sky130hd",
            "backend": "cloud_job",
        },
        tmp_path,
    )

    with session_scope(SessionContext(session_id, ws)):
        resp = sm.get_synthesis_status("synth_0001", workspace=ws)

    assert resp["status"] == "failed"
    assert "orchestrator lost" in resp["check_notes"]
    assert resp["recovered_from_index"] is True
    # Exactly one completion event, and the durable tombstone persisted.
    assert os.path.exists(os.path.join(run_dir, "completion.event"))
    assert [c for c in event_spy if c["tool_call_id"] == "completion:synth_0001"] == [
        {"tool_call_id": "completion:synth_0001"}
    ]

    # A second read stays failed — status never regresses back to queued/running.
    with session_scope(SessionContext(session_id, ws)):
        again = sm.get_synthesis_status("synth_0001", workspace=ws)
    assert again["status"] == "failed"
    assert len([c for c in event_spy if c["tool_call_id"] == "completion:synth_0001"]) == 1


def test_cross_instance_within_ceiling_adopts_running_not_queued(
    tmp_path, durable_store, event_spy
):
    """Forward adoption without false-failing: a run still inside its ceiling is
    reported 'running' (adopted from durable), never the stale local 'queued'."""
    session_id = "sess-y"
    ws, _run_dir = _reader_with_queued_local(tmp_path, dispatched_ago=100.0, timeout_sec=600)
    _push_remote(
        durable_store,
        f"{session_id}/synth_0001",
        {
            "run_id": "synth_0001",
            "status": "running",
            "dispatched_at": _iso_ago(100.0),
            "created_at": _iso_ago(90.0),
            "timeout_sec": 600,
            "max_stage": "finish",
            "top_module": "counter",
            "platform": "sky130hd",
            "backend": "cloud_job",
        },
        tmp_path,
    )

    with session_scope(SessionContext(session_id, ws)):
        resp = sm.get_synthesis_status("synth_0001", workspace=ws)

    assert resp["status"] == "running"  # NOT "queued" — no backward regression
    assert not [c for c in event_spy if c["tool_call_id"] == "completion:synth_0001"]
