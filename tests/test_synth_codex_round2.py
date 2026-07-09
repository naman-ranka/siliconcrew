"""Wave 9 round-2 (codex) regression tests — findings C1-C4.

C1  One stage truth in the PAYLOAD: for non-terminal runs the response's
    ``stages`` table carries the file-derived statuses (overlaid on a COPY of
    the persisted table, artifacts detail kept; meta on disk never written by
    the read). For a FAILED run stage_progress_from_files marks the first
    unfinished in-plan stage "failed" (not "running") so stage /
    current_stage / stage_history / stages agree.
C2  Durable run meta is readable back: ObjectStore.get_file + the
    reconciler's remote-meta pre-check let instance B answer terminal from
    the meta instance A pushed, persist it locally, and emit the completion
    event exactly once.
C3  Adoption does not wait for the ceiling: with no live future, cloud
    outputs at <handle>/out finalize the run COMPLETED on the very next read
    even though the timeout ceiling is far from expired.
C4  get_synthesis_status's future-exception path persists the failed
    tombstone (local + durable), appends the index entry, and emits exactly
    one completion event — a later fresh reader agrees from disk alone.
"""
import json
import os
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

import pytest

from src.platform_engines.workspace_provider import InMemoryObjectStore
from src.tools import synthesis_manager as sm
from src.utils.session_context import SessionContext, session_scope


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _write(path: str, content: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


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
    """Record every completion event log_tool_result would write."""
    import src.utils.attempt_logger as attempt_logger

    calls = []

    def _record(workspace, session_id, source, tool, result, status="success", **kwargs):
        calls.append({
            "workspace": workspace,
            "tool": tool,
            "result": result,
            "status": status,
            "tool_call_id": kwargs.get("tool_call_id"),
        })

    monkeypatch.setattr(attempt_logger, "log_tool_result", _record)
    return calls


def _mid_flow_run_dir(workspace: str, run_id: str = "synth_0001") -> str:
    """constraints + synth done (fresh markers), floorplan not yet."""
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write(
        os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.odb"),
        "odb",
    )
    return run_dir


# ---------------------------------------------------------------------------
# C1: payload coherence — stages overlay for non-terminal runs
# ---------------------------------------------------------------------------


def test_running_run_stages_overlay_matches_history(tmp_path):
    """The persisted stages table lags (readers never write meta); the
    RESPONSE overlays the file-derived statuses so stages and stage_history
    tell one story, keeping the persisted artifacts detail."""
    workspace = str(tmp_path)
    run_dir = _mid_flow_run_dir(workspace)
    stages = sm._init_stage_metadata()
    stages["synth"]["artifacts"] = {"odb": "orfs_results/sky130hd/counter/base/1_synth.odb"}
    persisted = {
        "run_id": "synth_0001",
        "status": "running",
        "dispatched_at": _iso_ago(60.0),
        "created_at": _iso_ago(55.0),
        "timeout_sec": 600,
        "max_stage": "finish",
        "current_stage": "constraints",  # stale — the worker has not persisted since
        "top_module": "counter",
        "platform": "sky130hd",
        "stages": stages,
    }
    _write(os.path.join(run_dir, "run_meta.json"), json.dumps(persisted))

    resp = sm.get_synthesis_status("synth_0001", workspace=workspace)

    assert resp["status"] == "running"
    history = {h["stage"]: h["status"] for h in resp["stage_history"]}
    assert history["constraints"] == "completed"
    assert history["synth"] == "completed"
    assert history["floorplan"] == "running"
    # ONE truth: every stage in the payload table matches the history.
    for stage, entry in resp["stages"].items():
        assert entry["status"] == history[stage], stage
    # Persisted artifact detail survives the overlay.
    assert resp["stages"]["synth"]["artifacts"] == {
        "odb": "orfs_results/sky130hd/counter/base/1_synth.odb"
    }
    assert resp["stage"] == resp["current_stage"] == "floorplan"

    # Response-only: the read never wrote the overlay back to run_meta.json.
    on_disk = json.loads(open(os.path.join(run_dir, "run_meta.json")).read())
    assert on_disk["stages"]["synth"]["status"] == "pending"
    assert on_disk["current_stage"] == "constraints"


def test_failed_run_history_marks_failed_stage_not_running(tmp_path):
    """meta.status == failed: the first unfinished in-plan stage reads
    'failed' in stage_history, and stage == current_stage == that stage.
    Terminal runs keep the persisted stages table authoritative."""
    workspace = str(tmp_path)
    run_dir = _mid_flow_run_dir(workspace)
    stages = sm._init_stage_metadata()
    for s in ("constraints", "synth"):
        stages[s]["status"] = "completed"
    stages["floorplan"]["status"] = "failed"
    persisted = {
        "run_id": "synth_0001",
        "status": "failed",
        "dispatched_at": _iso_ago(120.0),
        "created_at": _iso_ago(115.0),
        "finished_at": _iso_ago(10.0),
        "timeout_sec": 600,
        "max_stage": "finish",
        "current_stage": "floorplan",
        "check_notes": "floorplan crashed",
        "top_module": "counter",
        "platform": "sky130hd",
        "stages": stages,
    }
    _write(os.path.join(run_dir, "run_meta.json"), json.dumps(persisted))

    resp = sm.get_synthesis_status("synth_0001", workspace=workspace)

    assert resp["status"] == "failed"
    history = {h["stage"]: h["status"] for h in resp["stage_history"]}
    assert history["floorplan"] == "failed"
    assert "running" not in history.values()
    assert resp["stage"] == "floorplan"
    assert resp["current_stage"] == "floorplan"
    # Terminal → persisted-authoritative table, coherent with the history.
    assert resp["stages"]["floorplan"]["status"] == "failed"


def test_completed_run_stages_stay_persisted_authoritative(tmp_path):
    """Terminal completed: the worker refreshed the table at finalize — the
    response returns it untouched (no overlay)."""
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    _write(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
        "Chip area for module '\\counter': 12.0\n10 1.0 cells\n",
    )
    stages = sm._init_stage_metadata()
    stages["constraints"]["status"] = "completed"
    stages["synth"]["status"] = "completed"
    for s in ("floorplan", "place", "cts", "grt", "route", "finish"):
        stages[s]["status"] = "skipped"
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": "synth_0001",
            "status": "completed",
            "max_stage": "synth",
            "current_stage": "synth",
            "dispatched_at": _iso_ago(300.0),
            "top_module": "counter",
            "platform": "sky130hd",
            "stages": stages,
        }),
    )

    resp = sm.get_synthesis_status("synth_0001", workspace=workspace)

    assert resp["status"] == "completed"
    assert resp["stage"] == resp["current_stage"] == "synth"
    assert resp["stages"]["synth"]["status"] == "completed"
    assert {s for s, m in resp["stages"].items() if m["status"] == "skipped"} == {
        "floorplan", "place", "cts", "grt", "route", "finish",
    }


# ---------------------------------------------------------------------------
# C2: cross-instance read-back of the durable run meta
# ---------------------------------------------------------------------------


def _terminal_meta(run_id: str = "synth_0001") -> dict:
    stages = sm._init_stage_metadata()
    for s in sm.PD_STAGE_SEQUENCE:
        stages[s]["status"] = "completed"
    return {
        "run_id": run_id,
        "status": "completed",
        "dispatched_at": _iso_ago(900.0),
        "created_at": _iso_ago(890.0),
        "finished_at": _iso_ago(60.0),
        "timeout_sec": 600,
        "max_stage": "finish",
        "current_stage": "finish",
        "top_module": "counter",
        "platform": "sky130hd",
        "elapsed_sec": 830.0,
        "summary_metrics": {"wns_ns": 0.12, "cell_count": 10},
        "stages": stages,
    }


@pytest.mark.parametrize("local_state", ["running", "missing"])
def test_instance_b_adopts_terminal_meta_pushed_by_instance_a(
    tmp_path, durable_store, event_spy, local_state
):
    session_id = "sess-c2"
    run_id = "synth_0001"
    meta_a = _terminal_meta(run_id)

    # Instance A: finalize + durable push, then its scratch dies with it.
    ws_a = str(tmp_path / "instance_a")
    run_dir_a = os.path.join(ws_a, "synth_runs", run_id)
    _write(os.path.join(run_dir_a, "run_meta.json"), json.dumps(meta_a))
    with session_scope(SessionContext(session_id, ws_a)):
        sm._push_durable_run_meta(run_dir_a, meta_a)
    assert f"{session_id}/{run_id}/meta/{sm.RUN_META_FILENAME}" in durable_store._files

    # Instance B: same session, fresh scratch; no live future in _JOBS.
    ws_b = str(tmp_path / "instance_b")
    run_dir_b = os.path.join(ws_b, "synth_runs", run_id)
    os.makedirs(run_dir_b, exist_ok=True)
    if local_state == "running":
        _write(
            os.path.join(run_dir_b, "run_meta.json"),
            json.dumps({
                "run_id": run_id,
                "status": "running",
                "dispatched_at": _iso_ago(60.0),
                "timeout_sec": 600,
            }),
        )
    assert sm._job_key(ws_b, run_id) not in sm._JOBS

    with session_scope(SessionContext(session_id, ws_b)):
        resp = sm.get_synthesis_status(run_id, workspace=ws_b)

    # Terminal answer from the durable meta, persisted locally.
    assert resp["status"] == "completed"
    assert resp["summary_metrics"] == {"wns_ns": 0.12, "cell_count": 10}
    on_disk = json.loads(open(os.path.join(run_dir_b, "run_meta.json")).read())
    assert on_disk["status"] == "completed"

    # Exactly one completion event on adoption (the announcing instance's own
    # event may have died with its scratch; the deterministic id dedupes any
    # cross-instance double at read time).
    completions = [c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]
    assert len(completions) == 1
    assert os.path.exists(os.path.join(run_dir_b, "completion.event"))

    # Second read: terminal from local disk, no second event.
    with session_scope(SessionContext(session_id, ws_b)):
        again = sm.get_synthesis_status(run_id, workspace=ws_b)
    assert again["status"] == "completed"
    assert len([c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]) == 1


def test_remote_non_terminal_meta_never_overrides_local(tmp_path, durable_store, event_spy):
    """Precedence rule: a NON-terminal remote meta only fills a MISSING local
    one; it never replaces existing local state."""
    session_id = "sess-c2b"
    run_id = "synth_0001"
    ws = str(tmp_path / "ws")
    run_dir = os.path.join(ws, "synth_runs", run_id)
    local = {
        "run_id": run_id,
        "status": "running",
        "dispatched_at": _iso_ago(30.0),
        "created_at": _iso_ago(25.0),
        "timeout_sec": 600,
        "check_notes": "local truth",
    }
    _write(os.path.join(run_dir, "run_meta.json"), json.dumps(local))
    # Remote copy is an OLDER non-terminal milestone.
    remote_src = tmp_path / "remote_meta.json"
    remote_src.write_text(json.dumps({"run_id": run_id, "status": "queued"}), encoding="utf-8")
    durable_store.put_file(f"{session_id}/{run_id}/meta/{sm.RUN_META_FILENAME}", str(remote_src))

    with session_scope(SessionContext(session_id, ws)):
        resp = sm.get_synthesis_status(run_id, workspace=ws)

    assert resp["status"] == "running"
    on_disk = json.loads(open(os.path.join(run_dir, "run_meta.json")).read())
    assert on_disk["check_notes"] == "local truth"
    assert not [c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]


# ---------------------------------------------------------------------------
# C3: adoption does not wait for the ceiling
# ---------------------------------------------------------------------------


def test_cloud_outputs_adopted_before_ceiling(tmp_path, durable_store, event_spy):
    """Running meta, NO live future, <handle>/out present, ceiling NOT
    reached: the next read finalizes COMPLETED immediately instead of showing
    'running' until the timeout expires."""
    session_id = "sess-c3"
    run_id = "synth_0001"
    ws = str(tmp_path / "ws")
    run_dir = os.path.join(ws, "synth_runs", run_id)
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": run_id,
            "status": "running",
            "dispatched_at": _iso_ago(30.0),  # ceiling (600s + grace) far away
            "created_at": _iso_ago(25.0),
            "timeout_sec": 600,
            "max_stage": "synth",
            "top_module": "counter",
            "platform": "sky130hd",
            "backend": "cloud_job",
        }),
    )

    # The Job uploaded its outputs; the orchestrating instance died before
    # stage_out — the synth marker only exists remotely.
    job_out = tmp_path / "job_out"
    marker = job_out / "orfs_reports" / "sky130hd" / "counter" / "base" / "synth_stat.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("Chip area for module '\\counter': 12.0\n10 1.0 cells\n", encoding="utf-8")
    durable_store.put_tree(f"{session_id}/{run_id}/out", str(job_out))

    with session_scope(SessionContext(session_id, ws)):
        resp = sm.get_synthesis_status(run_id, workspace=ws)

    assert resp["status"] == "completed"
    assert os.path.isfile(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt")
    )
    on_disk = json.loads(open(os.path.join(run_dir, "run_meta.json")).read())
    assert on_disk["status"] == "completed"
    assert len([c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]) == 1


def test_no_outputs_within_ceiling_still_running(tmp_path, durable_store):
    """Same young run WITHOUT uploaded outputs: honestly still running (the
    early adoption must not loosen the death verdict)."""
    session_id = "sess-c3b"
    run_id = "synth_0001"
    ws = str(tmp_path / "ws")
    run_dir = os.path.join(ws, "synth_runs", run_id)
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": run_id,
            "status": "running",
            "dispatched_at": _iso_ago(30.0),
            "created_at": _iso_ago(25.0),
            "timeout_sec": 600,
            "max_stage": "synth",
            "backend": "cloud_job",
        }),
    )

    with session_scope(SessionContext(session_id, ws)):
        resp = sm.get_synthesis_status(run_id, workspace=ws)

    assert resp["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


# ---------------------------------------------------------------------------
# C4: future-exception path persists the tombstone
# ---------------------------------------------------------------------------


def test_future_exception_persists_tombstone_index_and_one_event(tmp_path, event_spy):
    ws = str(tmp_path)
    run_id = "synth_0001"
    run_dir = os.path.join(ws, "synth_runs", run_id)
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": run_id,
            "status": "queued",
            "dispatched_at": _iso_ago(10.0),
            "timeout_sec": 600,
            "max_stage": "finish",
            "current_stage": "constraints",
            "stages": sm._init_stage_metadata(),
        }),
    )
    future: Future = Future()
    future.set_exception(RuntimeError("executor exploded"))
    key = sm._job_key(ws, run_id)
    sm._JOBS[key] = {
        "future": future,
        "workspace": ws,
        "run_dir": run_dir,
        "created_at": _iso_ago(10.0),
    }
    try:
        resp = sm.get_synthesis_status(run_id, workspace=ws)
    finally:
        sm._JOBS.pop(key, None)

    assert resp["status"] == "failed"
    assert "Job execution error: executor exploded" in resp["check_notes"]

    # Tombstone persisted: terminal meta + refreshed stage table on disk.
    on_disk = json.loads(open(os.path.join(run_dir, "run_meta.json")).read())
    assert on_disk["status"] == "failed"
    assert "Job execution error: executor exploded" in on_disk["check_notes"]
    assert on_disk.get("finished_at")
    assert isinstance(on_disk.get("stages"), dict)

    # Index entry + exactly one completion event.
    index = sm._load_index(ws)
    entries = {r["run_id"]: r["status"] for r in index.get("runs", [])}
    assert entries.get(run_id) == "failed"
    assert len([c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]) == 1
    failed_events = [c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]
    assert failed_events[0]["status"] == "error"

    # A SECOND fresh reader (no _JOBS entry, e.g. another instance restart)
    # sees the same failed truth from disk, without a second announcement.
    again = sm.get_synthesis_status(run_id, workspace=ws)
    assert again["status"] == "failed"
    assert "Job execution error" in again["check_notes"]
    assert len([c for c in event_spy if c["tool_call_id"] == f"completion:{run_id}"]) == 1


def test_future_exception_pushes_durable_tombstone(tmp_path, durable_store, event_spy):
    """Cloud mode: the exception tombstone reaches <handle>/meta too, so
    another instance adopts 'failed' (C2) instead of re-deriving state."""
    session_id = "sess-c4"
    run_id = "synth_0001"
    ws = str(tmp_path)
    run_dir = os.path.join(ws, "synth_runs", run_id)
    _write(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": run_id,
            "status": "running",
            "dispatched_at": _iso_ago(10.0),
            "timeout_sec": 600,
        }),
    )
    future: Future = Future()
    future.set_exception(RuntimeError("boom"))
    key = sm._job_key(ws, run_id)
    sm._JOBS[key] = {"future": future, "workspace": ws, "run_dir": run_dir, "created_at": _iso_ago(10.0)}
    try:
        with session_scope(SessionContext(session_id, ws)):
            resp = sm.get_synthesis_status(run_id, workspace=ws)
    finally:
        sm._JOBS.pop(key, None)

    assert resp["status"] == "failed"
    pushed = json.loads(durable_store._files[f"{session_id}/{run_id}/meta/{sm.RUN_META_FILENAME}"])
    assert pushed["status"] == "failed"
    assert "Job execution error: boom" in pushed["check_notes"]


# ---------------------------------------------------------------------------
# C2 plumbing: get_file mirrors put_file's key scheme
# ---------------------------------------------------------------------------


def test_inmemory_get_file_roundtrip(tmp_path):
    store = InMemoryObjectStore()
    src = tmp_path / "run_meta.json"
    src.write_text('{"status": "completed"}', encoding="utf-8")
    key = "sess/synth_0001/meta/run_meta.json"

    dest = tmp_path / "pulled" / "run_meta.json"
    assert store.get_file(key, str(dest)) is False  # absent → False, no file
    assert not dest.exists()

    store.put_file(key, str(src))
    assert store.get_file(key, str(dest)) is True
    assert dest.read_text(encoding="utf-8") == '{"status": "completed"}'

    # Tar-blob keys are a different namespace: get_file never sees put_tree.
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_text("x", encoding="utf-8")
    store.put_tree("sess/synth_0001/out", str(tree))
    assert store.get_file("sess/synth_0001/out", str(tmp_path / "nope")) is False
