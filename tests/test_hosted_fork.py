"""Hosted fork (Wave 11, Item 3) — cloud workspace + gcs/local template source.

Forced-hosted harness (no live GCS/Cloud Run): a ``CloudWorkspaceProvider`` over
an ``InMemoryObjectStore`` for the WORKSPACE side, and a ``GcsTemplateSource``
over a SECOND in-memory store the ``publish_templates`` tool pre-populated with a
real-shaped bundle (source + binaries archives + index). ``_is_cloud_workspace``
is toggled on directly (it is a thin settings read); the workspace provider and
template source are injected via their ``set_*`` seams and ALWAYS restored in
teardown (with ``reset_settings_cache``) so nothing leaks into sibling tests.

No pytest-asyncio: the fork backend is synchronous; the REST leg (to_thread,
error mapping) lives in the commit-(c) additions at the bottom of this file.
"""
import json
import os
import shutil

import pytest

from src.utils.session_manager import SessionManager
from src.utils import templates as T
from src.utils.bundles import BundleTooLarge
from src.platform_engines import settings as settings_mod
from src.platform_engines import template_source as TS
from src.platform_engines.template_source import (
    GcsTemplateSource,
    LocalTemplateSource,
    TemplateStoreUnavailable,
)
from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
    set_workspace_provider,
)
from src.tools.synthesis_manager import _find_netlist
from scripts import split_bundle_binaries as SPLIT
from scripts import publish_templates as PUB


# ---------------------------------------------------------------------------
# Recording object store — spies on every mutating call (tenancy proof).
# ---------------------------------------------------------------------------


class RecordingStore(InMemoryObjectStore):
    """InMemoryObjectStore that records the KEY of every write/delete."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list = []

    def put_tree(self, key, local_dir):
        self.writes.append(key)
        super().put_tree(key, local_dir)

    def put_file(self, key, local_path):
        self.writes.append(key)
        super().put_file(key, local_path)

    def delete_tree(self, key):
        self.writes.append(("delete_tree", key))
        super().delete_tree(key)

    def delete_file(self, key):
        self.writes.append(("delete_file", key))
        super().delete_file(key)


# ---------------------------------------------------------------------------
# Bundle builders + gcs publish (all in-memory; no live GCS import)
# ---------------------------------------------------------------------------


def _w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


def _make_full_bundle(root, tid="demo_fifo", top="fifo", *, with_inputs_rtl=True):
    """A realistic FULL bundle (binaries present): RTL/tb/manifest + a completed
    synth run whose gate netlist lives under ``orfs_results`` and, optionally, a
    pre-synthesis ``inputs/<top>.v`` (the A15 trap)."""
    bundle = os.path.join(root, tid)
    ws = os.path.join(bundle, "workspace")
    _w(os.path.join(bundle, "template.json"), {
        "id": tid, "name": "Demo FIFO", "description": "A tiny FIFO example.",
        "highlights": ["Lints clean"], "top_module": top, "platform": "sky130hd",
    })
    _w(os.path.join(ws, f"{top}.v"), f"module {top}(); endmodule\n")
    _w(os.path.join(ws, f"{top}_tb.v"), f"module {top}_tb(); endmodule\n")
    _w(os.path.join(ws, "manifest.json"), {
        "sessionId": "ORIGINAL_SOURCE_SESSION",
        "files": [{"name": f"{top}.v", "role": "rtl", "path": f"{top}.v"}],
        "synthTop": top, "simTop": f"{top}_tb",
    })
    _w(os.path.join(ws, "attempt_events.jsonl"),
       '{"event_type":"tool_call","session_id":"ORIGINAL_SOURCE_SESSION"}\n')
    run = os.path.join(ws, "synth_runs", "synth_0001")
    _w(os.path.join(run, "orfs_results", "sky130hd", top, "base", "6_final.v"),
       f"module {top}(); endmodule // gate netlist\n")
    if with_inputs_rtl:
        # RTL input stays in git (not under orfs_results) — _find_netlist would
        # otherwise latch onto it in a binary-less fork (the A15 dishonesty).
        _w(os.path.join(run, "inputs", f"{top}.v"), f"module {top}(); endmodule // rtl\n")
    _w(os.path.join(run, "run_meta.json"), {
        "id": "synth_0001", "status": "completed", "top_module": top,
        "netlist_path": r"C:\some\other\machine\orfs_results\6_final.v",
    })
    _w(os.path.join(run, "completion.event"), "")
    return bundle, ws


def _make_split_bundle(root, tid="demo_fifo", top="fifo", *, with_inputs_rtl=True):
    """Build a full bundle then split its binaries out (writes .sc_binaries.json,
    deletes the orfs_results binaries) — the self-host-without-fetch shape."""
    _make_full_bundle(root, tid, top, with_inputs_rtl=with_inputs_rtl)
    SPLIT.split_bundle(os.path.join(root, tid), apply=True)
    return root


def _publish_gcs(store, tmp_path, tid="demo_fifo", top="fifo"):
    """Publish a real-shaped bundle (source+binaries archives+index) into ``store``.

    Mirrors the operator flow: source comes from a SPLIT tree, binaries from the
    pre-split (full) tree — exactly ``publish_templates --ref <split> --binaries-
    from <full>``.
    """
    full_root = os.path.join(tmp_path, "examples_full")
    split_root = os.path.join(tmp_path, "examples_split")
    _make_full_bundle(full_root, tid, top)
    shutil.copytree(os.path.join(full_root, tid), os.path.join(split_root, tid))
    SPLIT.split_bundle(os.path.join(split_root, tid), apply=True)
    PUB.publish(store, split_root, full_root, [tid], log=lambda *a, **k: None)
    return split_root, full_root


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


@pytest.fixture
def scratch(tmp_path):
    d = str(tmp_path / "scratch")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _restore_seams():
    """Always reset the injected engines + settings cache after each test."""
    yield
    set_workspace_provider(None)
    TS.set_template_source(None)
    settings_mod.reset_settings_cache()


def _go_cloud(monkeypatch):
    """Toggle the fork onto the cloud-workspace branch."""
    monkeypatch.setattr(T, "_is_cloud_workspace", lambda: True)


def _manifest_key(sid):
    return f"workspaces/{sid}/.sc_manifest.json"


# ---------------------------------------------------------------------------
# Happy path — cloud workspace + gcs source (WITH binaries)
# ---------------------------------------------------------------------------


def test_hosted_fork_happy_path(sm, scratch, tmp_path, monkeypatch):
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)

    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    tmpl_store.writes.clear()  # only care about writes DURING the fork
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid = T.fork_from_template(sm, "demo_fifo", user_id="alice")

    # Files landed in the provider scratch (the path tools actually read).
    ws = os.path.join(scratch, sid)
    assert os.path.isfile(os.path.join(ws, "fifo.v"))
    assert os.path.isfile(os.path.join(ws, "attempt_events.jsonl"))
    assert os.path.isfile(os.path.join(ws, ".sc_binaries.json"))
    gate = os.path.join(ws, "synth_runs", "synth_0001", "orfs_results", "sky130hd", "fifo", "base", "6_final.v")
    assert os.path.isfile(gate)  # binaries archive materialized

    # sync ran LAST → the workspace manifest is committed (adoptable by any instance).
    assert _manifest_key(sid) in ws_store._files

    # Identity leaks scrubbed; netlist re-derived into the fork's own run dir.
    manifest = json.load(open(os.path.join(ws, "manifest.json")))
    assert manifest["sessionId"] == ""
    meta = json.load(open(os.path.join(ws, "synth_runs", "synth_0001", "run_meta.json")))
    assert meta["netlist_path"] and os.path.exists(meta["netlist_path"])
    assert os.path.abspath(ws) in os.path.abspath(meta["netlist_path"])
    assert "machine" not in meta["netlist_path"]  # not the stale source-machine path

    # Provenance: workspace file AND the durable store copy.
    prov = T.read_provenance(ws)
    assert prov["id"] == "demo_fifo" and prov["forked_at"].endswith("+00:00")
    row = sm.get_session_metadata(sid, user_id="alice")
    assert json.loads(row["source_template"])["id"] == "demo_fifo"

    # Chat 1 seeded; owned by alice; invisible to bob.
    assert sm.count_threads(sid, user_id="alice") == 1
    assert sm.owns_session(sid, "alice")
    assert sm.get_session_metadata(sid, user_id="bob") is None

    # Template store was READ-ONLY throughout the fork.
    assert tmpl_store.writes == []


# ---------------------------------------------------------------------------
# A15 — binary-less fork must NOT re-derive netlist_path onto inputs/ RTL
# ---------------------------------------------------------------------------


def test_binary_less_fork_forces_netlist_none_not_inputs_rtl(sm, tmp_path):
    split_root = os.path.join(tmp_path, "examples")
    _make_split_bundle(split_root, "demo_fifo", "fifo", with_inputs_rtl=True)
    run_dir = os.path.join(split_root, "demo_fifo", "workspace", "synth_runs", "synth_0001")
    # Sanity: the gate netlist was split out and the RTL input remains.
    assert not os.path.exists(os.path.join(run_dir, "orfs_results", "sky130hd", "fifo", "base", "6_final.v"))
    assert os.path.isfile(os.path.join(run_dir, "inputs", "fifo.v"))
    # This assertion used to read `is not None` — it documented "the trap": pre-#56,
    # _find_netlist scanned inputs/ too and WOULD latch onto that RTL, so A15's rule
    # was the only thing standing between a fork and an RTL-as-netlist. #56 removed
    # the trap at its source (only the ORFS output tree holds a gate netlist), so the
    # two guards are now independent — defense in depth, not one rule carrying it.
    assert _find_netlist(run_dir, "fifo") is None

    # Self-host fork (examples_dir → local source); A15 runs regardless of engine.
    fid = T.fork_from_template(sm, "demo_fifo", examples_dir=split_root)
    ws = sm.get_workspace_path(fid)
    meta = json.load(open(os.path.join(ws, "synth_runs", "synth_0001", "run_meta.json")))
    assert meta["netlist_path"] is None  # honest: gate netlist split out, not RTL
    # The RTL input is still on disk (proving None came from the rule, not absence).
    assert os.path.isfile(os.path.join(ws, "synth_runs", "synth_0001", "inputs", "fifo.v"))


# ---------------------------------------------------------------------------
# Rollback — no adoptable half-fork survives a failure
# ---------------------------------------------------------------------------


class _RaisingSource:
    """A template source whose get() succeeds but materialize() explodes."""

    def __init__(self, exc):
        self._exc = exc

    def get(self, template_id):
        return {"id": template_id, "name": "Demo FIFO"}

    def materialize(self, template_id, dst_dir, **kw):
        os.makedirs(dst_dir, exist_ok=True)
        _w(os.path.join(dst_dir, "partial.txt"), "half-written")  # leave debris
        raise self._exc


def test_rollback_on_materialize_failure(sm, scratch, monkeypatch):
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)
    TS.set_template_source(_RaisingSource(RuntimeError("boom mid-materialize")))

    before = set(sm.get_all_sessions())
    with pytest.raises(RuntimeError):
        T.fork_from_template(sm, "demo_fifo", user_id="alice")

    # Session row gone, scratch gone, manifest never committed.
    assert set(sm.get_all_sessions()) == before
    assert not any(os.scandir(scratch)) if os.path.isdir(scratch) else True
    assert not any(k for k in ws_store._files if k.endswith(".sc_manifest.json"))


def test_rollback_on_sync_failure(sm, scratch, tmp_path, monkeypatch):
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    # Real materialization succeeds, then the commit (sync) blows up.
    monkeypatch.setattr(provider, "sync", lambda sid: (_ for _ in ()).throw(RuntimeError("commit failed")))
    set_workspace_provider(provider)

    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    before = set(sm.get_all_sessions())
    with pytest.raises(RuntimeError):
        T.fork_from_template(sm, "demo_fifo", user_id="alice")

    assert set(sm.get_all_sessions()) == before
    assert not any(os.scandir(scratch)) if os.path.isdir(scratch) else True
    assert _manifest_key_absent(ws_store)


def _manifest_key_absent(store) -> bool:
    return not any(k.endswith(".sc_manifest.json") for k in store._files)


# ---------------------------------------------------------------------------
# All-or-nothing (A6) — a gcs source that promised binaries but can't deliver
# ---------------------------------------------------------------------------


def test_gcs_missing_binaries_fails_all_or_nothing(sm, scratch, tmp_path, monkeypatch):
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    set_workspace_provider(CloudWorkspaceProvider(ws_store, scratch))

    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    # Drop the binaries archive: the index still promises it → all-or-nothing.
    tmpl_store.delete_tree("bundles/demo_fifo/binaries")
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    before = set(sm.get_all_sessions())
    with pytest.raises(TemplateStoreUnavailable):
        T.fork_from_template(sm, "demo_fifo", user_id="alice")
    # Full rollback: no session, no committed workspace.
    assert set(sm.get_all_sessions()) == before
    assert _manifest_key_absent(ws_store)


def test_gcs_corrupt_binaries_fails_sha_verify(sm, scratch, tmp_path, monkeypatch):
    """A4: a binaries archive whose bytes don't match .sc_binaries.json sha256
    is a corrupt/incomplete publish — materialize must reject it, not hand back a
    silently wrong-bytes fork. Repack the binaries blob with tampered content."""
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    set_workspace_provider(CloudWorkspaceProvider(ws_store, scratch))

    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    # Rebuild the binaries tree with corrupted content, re-put under the same key.
    corrupt_dir = os.path.join(tmp_path, "corrupt")
    gate = os.path.join(
        corrupt_dir, "synth_runs", "synth_0001", "orfs_results", "sky130hd", "fifo", "base", "6_final.v"
    )
    _w(gate, "TAMPERED — not the published bytes\n")
    tmpl_store.put_tree("bundles/demo_fifo/binaries", corrupt_dir)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    before = set(sm.get_all_sessions())
    with pytest.raises(TemplateStoreUnavailable):
        T.fork_from_template(sm, "demo_fifo", user_id="alice")
    assert set(sm.get_all_sessions()) == before  # rolled back
    assert _manifest_key_absent(ws_store)


# ---------------------------------------------------------------------------
# Mixed engines (A6) — destination and materialization are independent axes
# ---------------------------------------------------------------------------


def test_cloud_workspace_local_source_degrades_and_syncs(sm, scratch, tmp_path, monkeypatch):
    """Deployed split image, no TEMPLATES_BUCKET yet: cloud workspace + LOCAL
    (binary-less) source. Honest degradation — the fork succeeds, syncs, and the
    missing gate netlist resolves to None (not the inputs RTL)."""
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)

    split_root = os.path.join(tmp_path, "examples")
    _make_split_bundle(split_root, "demo_fifo", "fifo", with_inputs_rtl=True)

    sid = T.fork_from_template(sm, "demo_fifo", user_id="alice", examples_dir=split_root)

    ws = os.path.join(scratch, sid)
    assert os.path.isfile(os.path.join(ws, "fifo.v"))
    assert _manifest_key(sid) in ws_store._files  # synced
    meta = json.load(open(os.path.join(ws, "synth_runs", "synth_0001", "run_meta.json")))
    assert meta["netlist_path"] is None  # A15 honest degradation


def test_local_workspace_gcs_source(sm, tmp_path, monkeypatch):
    """Self-host forking FROM the bucket: local workspace + gcs source (no sync).
    The destination is the local workspace dir; materialization pulls the bucket
    archives into it."""
    monkeypatch.setattr(T, "_is_cloud_workspace", lambda: False)
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid = T.fork_from_template(sm, "demo_fifo", user_id="alice")
    ws = sm.get_workspace_path(sid)
    assert os.path.isfile(os.path.join(ws, "fifo.v"))
    gate = os.path.join(ws, "synth_runs", "synth_0001", "orfs_results", "sky130hd", "fifo", "base", "6_final.v")
    assert os.path.isfile(gate)  # binaries came from the bucket
    meta = json.load(open(os.path.join(ws, "synth_runs", "synth_0001", "run_meta.json")))
    assert meta["netlist_path"] and os.path.exists(meta["netlist_path"])


# ---------------------------------------------------------------------------
# Tenancy red-team — writes stay under the fork's own workspace prefix
# ---------------------------------------------------------------------------


def test_tenancy_all_writes_under_fork_prefix_template_store_read_only(sm, scratch, tmp_path, monkeypatch):
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    set_workspace_provider(CloudWorkspaceProvider(ws_store, scratch))

    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    tmpl_store.writes.clear()
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid = T.fork_from_template(sm, "demo_fifo", user_id="alice")

    # Every workspace-store op (writes AND the pre-hydrate orphan-purge deletes)
    # is under THIS fork's prefix — no other tenant's workspace, no template
    # bucket. Deletes are recorded as (op, key) tuples; writes as bare keys.
    prefix = f"workspaces/{sid}/"
    assert ws_store.writes, "sync must have written blobs + manifest"
    for entry in ws_store.writes:
        key = entry[1] if isinstance(entry, tuple) else entry
        assert key.startswith(prefix), entry
    # Template store saw zero writes (READ-ONLY browsing/materialization).
    assert tmpl_store.writes == []
    # Owner immutable: a second upsert by 'bob' cannot claim the fork.
    import datetime as _dt
    sm._store.upsert_session(sid, "bob", "x", "m", None, _dt.datetime.now())
    assert sm.get_session_metadata(sid, user_id="bob") is None
    assert sm.owns_session(sid, "alice")


# ---------------------------------------------------------------------------
# Re-fork / cross-tenant id reuse (adversarial review — CRITICAL leak+clobber).
# Fork ids are name-derived (slug of the template name), so every fork of the
# same template competes for ONE global id. On hosted, local disk is ephemeral
# per-instance while the metadata store + GCS are shared, so a name collision
# must be caught against the SHARED store — never the local dir — and a fork must
# never hydrate a foreign/orphaned object-storage workspace.
# ---------------------------------------------------------------------------


def _resync_with_file(provider, sid, relpath, content):
    """Write a user file into a synced fork's scratch and re-commit it, so the
    file lives in the committed object-storage workspace (what a later same-id
    fork would hydrate if the id were wrongly reused)."""
    ws = provider.workspace_for(sid)
    _w(os.path.join(ws, relpath), content)
    provider.sync(sid)


def test_refork_after_delete_is_not_contaminated_by_prior_session(sm, scratch, tmp_path, monkeypatch):
    """Sequence A: fork → add a private file → delete → re-fork the SAME template.
    The fresh fork must be pristine (no leftover file), even though delete leaves
    object storage behind (D7 GC deferred). Pre-fix this leaked the deleted
    session's private file into a 'pristine' fork."""
    _go_cloud(monkeypatch)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid1 = T.fork_from_template(sm, "demo_fifo", user_id="alice")
    _resync_with_file(provider, sid1, "SECRET_user_notes.txt", "alice private notes")
    assert os.path.isfile(os.path.join(scratch, sid1, "SECRET_user_notes.txt"))

    sm.delete_session(sid1, user_id="alice")

    sid2 = T.fork_from_template(sm, "demo_fifo", user_id="alice")
    assert sid2 == sid1  # id is free again → legitimately reused
    ws2 = os.path.join(scratch, sid2)
    assert not os.path.exists(os.path.join(ws2, "SECRET_user_notes.txt"))  # pristine
    assert os.path.isfile(os.path.join(ws2, "fifo.v"))  # real template content
    assert sm.owns_session(sid2, "alice")


def test_cross_tenant_fork_of_same_template_isolates_owner_and_workspace(tmp_path, scratch, monkeypatch):
    """Sequence B: alice forks a template and keeps it; bob forks the SAME
    template from a DIFFERENT instance (own ephemeral disk, shared Cloud SQL +
    GCS). Bob must get his OWN id + empty workspace — never alice's row, files,
    or a clobber of her committed workspace."""
    _go_cloud(monkeypatch)
    shared_db = str(tmp_path / "shared_state.db")
    sm_a = SessionManager(base_dir=str(tmp_path / "instanceA"), db_path=shared_db)
    sm_b = SessionManager(base_dir=str(tmp_path / "instanceB"), db_path=shared_db)

    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid_a = T.fork_from_template(sm_a, "demo_fifo", user_id="alice")
    _resync_with_file(provider, sid_a, "ALICE_SECRET.txt", "top secret")
    alice_manifest_gen = ws_store.generation(_manifest_key(sid_a))

    ws_store.writes.clear()  # isolate the writes bob's fork makes
    sid_b = T.fork_from_template(sm_b, "demo_fifo", user_id="bob")

    assert sid_b != sid_a  # bob did NOT adopt alice's id
    assert sm_b.owns_session(sid_b, "bob")
    assert sm_a.get_session_metadata(sid_b, user_id="alice") is None  # not alice's
    # Bob's workspace has the template, NOT alice's private file.
    ws_b = os.path.join(scratch, sid_b)
    assert os.path.isfile(os.path.join(ws_b, "fifo.v"))
    assert not os.path.exists(os.path.join(ws_b, "ALICE_SECRET.txt"))  # no leak
    # Alice still owns her session and her committed workspace is untouched.
    assert sm_a.owns_session(sid_a, "alice")
    assert ws_store.generation(_manifest_key(sid_a)) == alice_manifest_gen  # no clobber
    # Every workspace write during bob's fork stayed under bob's own prefix.
    bob_writes = [k for k in ws_store.writes if isinstance(k, str)]
    assert any(k.startswith(f"workspaces/{sid_b}/") for k in bob_writes)
    assert not any(k.startswith(f"workspaces/{sid_a}/") for k in bob_writes)


def test_concurrent_same_template_fork_race_insert_arbitrates(tmp_path, scratch, monkeypatch):
    """Genuine concurrent race (MAJOR residual from the first fix): two instances
    fork the same template; the name-derived pre-check is BLIND during the
    check-to-insert window (simulated). The atomic INSERT must arbitrate — the
    loser retries a distinct owned id and NEVER runs delete_workspace/sync on the
    winner's LIVE workspace. Pre-fix (upsert) the loser adopted alice's id and
    destroyed her committed workspace."""
    _go_cloud(monkeypatch)
    shared_db = str(tmp_path / "shared.db")
    sm_a = SessionManager(base_dir=str(tmp_path / "A"), db_path=shared_db)
    sm_b = SessionManager(base_dir=str(tmp_path / "B"), db_path=shared_db)
    ws_store = RecordingStore()
    provider = CloudWorkspaceProvider(ws_store, scratch)
    set_workspace_provider(provider)
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    sid_a = T.fork_from_template(sm_a, "demo_fifo", user_id="alice")
    _resync_with_file(provider, sid_a, "ALICE_SECRET.txt", "secret")
    alice_gen = ws_store.generation(_manifest_key(sid_a))

    # Blind pre-check on bob's instance for alice's id (the check-to-insert
    # window): only the atomic insert stands between bob and alice's data.
    orig = sm_b._store.get_session
    monkeypatch.setattr(
        sm_b._store, "get_session",
        lambda sid, user_id=None: None if sid == sid_a else orig(sid, user_id),
    )
    ws_store.writes.clear()
    sid_b = T.fork_from_template(sm_b, "demo_fifo", user_id="bob")

    assert sid_b != sid_a  # loser retried to a distinct id
    assert sm_b.owns_session(sid_b, "bob")
    # Alice's live workspace untouched — no delete/clobber under her prefix.
    assert ws_store.generation(_manifest_key(sid_a)) == alice_gen
    for entry in ws_store.writes:
        key = entry[1] if isinstance(entry, tuple) else entry
        assert not key.startswith(f"workspaces/{sid_a}/"), entry
    assert not os.path.exists(os.path.join(scratch, sid_b, "ALICE_SECRET.txt"))


def test_insert_session_raises_on_duplicate(tmp_path):
    """The atomic arbiter: a second insert of the same id raises DuplicateSession
    (the PK conflict), never a silent upsert."""
    from src.platform_engines.metadata_store import DuplicateSession
    import datetime as _dt

    shared_db = str(tmp_path / "db.sqlite")
    sm_a = SessionManager(base_dir=str(tmp_path / "a"), db_path=shared_db)
    sm_a.create_session("dup", user_id="alice")
    with pytest.raises(DuplicateSession):
        sm_a._store.insert_session("dup", "bob", "x", "m", None, _dt.datetime.now())
    assert sm_a.get_session_metadata("dup", user_id="alice")  # alice still owns it


def test_create_session_rejects_preexisting_global_row(tmp_path):
    """The root guard: create_session must refuse an id already in the shared
    store even when this instance's local disk is empty (the cross-instance
    hazard). Model two instances sharing one db."""
    shared_db = str(tmp_path / "db.sqlite")
    sm_a = SessionManager(base_dir=str(tmp_path / "a"), db_path=shared_db)
    sm_b = SessionManager(base_dir=str(tmp_path / "b"), db_path=shared_db)
    sm_a.create_session("shared-name", user_id="alice")
    # Bob's instance has no local dir for "shared-name" but the shared store does.
    with pytest.raises(FileExistsError):
        sm_b.create_session("shared-name", user_id="bob")


# ---------------------------------------------------------------------------
# REST leg (Item 3, commit c) — to_thread + error mapping + store-first reads
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402
import api  # noqa: E402


@pytest.fixture
def client(sm, monkeypatch):
    monkeypatch.setattr(api, "session_manager", sm)
    return TestClient(api.app)


def _go_cloud_rest(monkeypatch):
    monkeypatch.setattr(api.templates_mod, "_is_cloud_workspace", lambda: True)


def test_rest_hosted_fork_succeeds_and_chip_reads_from_store(client, sm, scratch, tmp_path, monkeypatch):
    """POST fork on a cloud workspace returns a ForkResponse; the forked-from
    chip resolves from the STORE (the workspace .source_template.json lives in
    the provider scratch, unreachable from the local get_workspace_path)."""
    _go_cloud_rest(monkeypatch)
    ws_store = RecordingStore()
    set_workspace_provider(CloudWorkspaceProvider(ws_store, scratch))
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    r = client.post("/api/templates/demo_fifo/fork")
    assert r.status_code == 200, r.text
    sid = r.json()["sessionId"]
    assert sid

    # The local workspace path has NO provenance file (fork wrote to scratch),
    # proving the chip came from the store row.
    assert not os.path.isfile(os.path.join(sm.get_workspace_path(sid), ".source_template.json"))
    got = client.get(f"/api/sessions/{sid}").json()
    assert got["source_template"]["id"] == "demo_fifo"
    # List + PATCH carry it too (invariant 7: populated data never blanks).
    listed = {s["id"]: s for s in client.get("/api/sessions").json()}
    assert listed[sid]["source_template"]["id"] == "demo_fifo"
    patched = client.patch(f"/api/sessions/{sid}", json={"name": "Renamed"}).json()
    assert patched["name"] == "Renamed"
    assert patched["source_template"]["id"] == "demo_fifo"


def test_rest_fork_missing_binaries_maps_to_503(client, sm, scratch, tmp_path, monkeypatch):
    _go_cloud_rest(monkeypatch)
    set_workspace_provider(CloudWorkspaceProvider(RecordingStore(), scratch))
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    tmpl_store.delete_tree("bundles/demo_fifo/binaries")  # promised but absent
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))

    r = client.post("/api/templates/demo_fifo/fork")
    assert r.status_code == 503, r.text
    assert "unreachable" in r.json()["detail"].lower()
    assert sm.get_all_sessions() == []  # rollback ran


def test_rest_fork_guard_failure_maps_to_500(client, sm, scratch, monkeypatch):
    _go_cloud_rest(monkeypatch)
    set_workspace_provider(CloudWorkspaceProvider(RecordingStore(), scratch))
    TS.set_template_source(_RaisingSource(BundleTooLarge("ceiling exceeded")))

    r = client.post("/api/templates/demo_fifo/fork")
    assert r.status_code == 500, r.text
    assert sm.get_all_sessions() == []  # rollback ran


def test_rest_fork_unknown_template_still_404(client, scratch, tmp_path, monkeypatch):
    _go_cloud_rest(monkeypatch)
    set_workspace_provider(CloudWorkspaceProvider(RecordingStore(), scratch))
    tmpl_store = RecordingStore()
    _publish_gcs(tmpl_store, tmp_path)
    TS.set_template_source(GcsTemplateSource(bucket="ignored", store=tmpl_store))
    assert client.post("/api/templates/ghost/fork").status_code == 404


def test_rest_provenance_file_fallback_when_store_null(client, sm):
    """A pre-existing self-host fork (provenance file, no store column) still
    lights the chip — the file fallback path, exercised independently."""
    sid = sm.create_session("legacy")
    _w(os.path.join(sm.get_workspace_path(sid), ".source_template.json"),
       {"id": "legacy_tmpl", "name": "Legacy", "forked_at": "2026-01-01T00:00:00+00:00"})
    assert sm.get_session_metadata(sid).get("source_template") is None  # no store value
    got = client.get(f"/api/sessions/{sid}").json()
    assert got["source_template"]["id"] == "legacy_tmpl"
