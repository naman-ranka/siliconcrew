"""Wave 9 run_id-only contract: dispatch-time meta, file-derived stage
progress, unknown-run answers, and completion-event dedupe at read time.

The run directory is the database: a queued run must be visible (and
tombstone-able) out-of-process from second zero, and every status answer has
the same shape whether it came from process memory or from disk.
"""
import json
import os
import time
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

from src.tools import synthesis_manager as sm
from src.api.activity import build_activity_events


class HeldExecutor:
    """Accepts submissions but never runs them — the dispatched run stays
    queued (Future.done() is False) for as long as the test needs."""

    def __init__(self):
        self.pending = []

    def submit(self, fn, *args):
        f: Future = Future()
        self.pending.append((f, fn, args))
        return f


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _write(path: str, content: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# --------------------------------------------------------------------------
# Dispatch-time run_meta: queued visibility from second zero
# --------------------------------------------------------------------------


def test_dispatch_writes_queued_meta_before_submit(tmp_path):
    workspace = str(tmp_path)
    executor = HeldExecutor()
    sm.set_job_executor(executor)
    try:
        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=["counter.v"],
            top_module="counter",
            platform="sky130hd",
        )

        # Dispatch return: run_id only — no job_id anywhere in the payload.
        assert started["run_id"] == "synth_0001"
        assert started["status"] == "queued"
        assert "job_id" not in started
        assert started["timeout_sec"] == sm.SYNTH_HARD_TIMEOUT_SEC
        assert started["poll_after_sec"] == sm.POLL_BACKOFF_START_SEC

        # run_meta.json exists IMMEDIATELY (worker never ran: HeldExecutor).
        meta_path = os.path.join(workspace, "synth_runs", "synth_0001", "run_meta.json")
        assert os.path.exists(meta_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["status"] == "queued"
        assert meta["dispatched_at"]
        assert meta["timeout_sec"] == sm.SYNTH_HARD_TIMEOUT_SEC
        assert meta["top_module"] == "counter"
        assert meta["platform"] == "sky130hd"
        assert meta["max_stage"] == "finish"
        assert set(meta["stages"].keys()) == set(sm.PD_STAGE_SEQUENCE)
        assert meta["backend"]

        # In-process read: live future (not done) → queued via memory.
        status = sm.get_synthesis_status("synth_0001", workspace=workspace)
        assert status["status"] == "queued"
        assert status["run_id"] == "synth_0001"
        assert status["dispatched_at"] == meta["dispatched_at"]
        assert status["timeout_sec"] == meta["timeout_sec"]

        # Out-of-process read (another instance never saw the dispatch):
        # clear the memory cache — disk meta answers, NOT unknown_run.
        sm._JOBS.clear()
        sm._POLL_CACHE.clear()
        recovered = sm.get_synthesis_status("synth_0001", workspace=workspace)
        assert recovered.get("error") is None
        assert recovered["status"] == "queued"
        assert recovered["recovered_from_index"] is True
        assert recovered["dispatched_at"] == meta["dispatched_at"]
    finally:
        sm.set_job_executor(None)


def test_retry_dispatch_returns_run_id_only(tmp_path):
    workspace = str(tmp_path)
    parent = os.path.join(workspace, "synth_runs", "synth_0001")
    results = os.path.join(parent, "orfs_results", "sky130hd", "demo_top", "base")
    _write(os.path.join(results, "1_synth.odb"), "odb")
    _write(os.path.join(results, "1_synth.sdc"), "sdc")
    _write(
        os.path.join(parent, "run_meta.json"),
        json.dumps({
            "run_id": "synth_0001", "status": "completed", "max_stage": "synth",
            "top_module": "demo_top", "platform": "sky130hd",
        }),
    )

    executor = HeldExecutor()
    sm.set_job_executor(executor)
    try:
        started = sm.retry_pd_job(
            workspace=workspace,
            source_run_id="synth_0001",
            start_stage="floorplan",
            max_stage="floorplan",
        )
        assert started["status"] == "queued"
        assert started["run_id"] == "synth_0002"
        assert "job_id" not in started
        assert started["mode"] == "pd_retry"
        assert started["source_run_id"] == "synth_0001"

        # Same dispatch-time meta contract as a first run.
        with open(os.path.join(workspace, "synth_runs", "synth_0002", "run_meta.json")) as f:
            meta = json.load(f)
        assert meta["status"] == "queued"
        assert meta["dispatched_at"]
        assert meta["mode"] == "pd_retry"
        assert meta["source_run_id"] == "synth_0001"
    finally:
        sm.set_job_executor(None)


# --------------------------------------------------------------------------
# stage_progress_from_files: the deterministic file→stage matrix
# --------------------------------------------------------------------------


def _results(run_dir: str) -> str:
    return os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")


def test_stage_progress_mid_flow(tmp_path):
    """synth + floorplan markers present → place is the current running stage."""
    run_dir = str(tmp_path)
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write(os.path.join(_results(run_dir), "1_synth.odb"), "odb")
    _write(os.path.join(_results(run_dir), "2_floorplan.odb"), "odb")
    meta = {"status": "running", "max_stage": "finish", "dispatched_at": _iso_ago(60.0)}

    out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "completed"
    assert history["synth"] == "completed"
    assert history["floorplan"] == "completed"
    assert history["place"] == "running"
    for stage in ["cts", "grt", "route", "finish"]:
        assert history[stage] == "pending", stage
    assert out["current_stage"] == "place"
    # Completed stages carry their marker's end timestamp.
    by_stage = {h["stage"]: h for h in out["stage_history"]}
    assert by_stage["synth"]["ended_at"]


def test_stage_progress_complete_bounded_run(tmp_path):
    """All markers up to max_stage present → the run sits AT its bound;
    stages past the bound are honestly 'skipped'."""
    run_dir = str(tmp_path)
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write(os.path.join(_results(run_dir), "1_synth.odb"), "odb")
    meta = {"status": "completed", "max_stage": "synth", "dispatched_at": _iso_ago(60.0)}

    out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "completed"
    assert history["synth"] == "completed"
    for stage in ["floorplan", "place", "cts", "grt", "route", "finish"]:
        assert history[stage] == "skipped", stage
    assert out["current_stage"] == "synth"


def test_stage_progress_retry_marks_parent_checkpoints_inherited(tmp_path):
    """Retry runs copy parent checkpoints with shutil.copy2 (mtimes
    preserved): anything older than THIS run's dispatch is 'inherited',
    never this run's progress/timing."""
    run_dir = str(tmp_path)
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write(os.path.join(_results(run_dir), "1_synth.odb"), "odb")   # parent's
    _write(os.path.join(_results(run_dir), "2_floorplan.odb"), "odb")  # this run's
    dispatched_ts = time.time() - 60.0
    meta = {
        "status": "running",
        "retry_max_stage": "finish",
        "dispatched_at": datetime.fromtimestamp(dispatched_ts, tz=timezone.utc).isoformat(),
    }
    # Pre-dispatch mtimes for the copied-in prerequisites.
    old = dispatched_ts - 3600.0
    os.utime(os.path.join(run_dir, "constraints.sdc"), (old, old))
    os.utime(os.path.join(_results(run_dir), "1_synth.odb"), (old, old))

    out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "inherited"
    assert history["synth"] == "inherited"
    assert history["floorplan"] == "completed"  # written after dispatch → this run's work
    assert history["place"] == "running"
    assert out["current_stage"] == "place"


# --------------------------------------------------------------------------
# Unknown run
# --------------------------------------------------------------------------


def test_unknown_run_id_answers_unknown_run(tmp_path):
    out = sm.get_synthesis_status("synth_9999", workspace=str(tmp_path))
    assert out["status"] == "failed"
    assert out["error"] == "unknown_run"
    assert out["run_id"] == "synth_9999"


# --------------------------------------------------------------------------
# Activity feed: cross-instance completion dedupe by deterministic id
# --------------------------------------------------------------------------


def test_duplicate_completion_orphan_results_collapse_to_one_event():
    dup = {
        "event_type": "tool_result",
        "source": "system",
        "tool": "synthesis_run",
        "tool_call_id": "completion:synth_0001",
        "ts": "2026-07-04T12:00:00+00:00",
        "status": "success",
        "result": "synth_0001 completed · WNS 0.12ns",
        "arguments": {"run_id": "synth_0001"},
    }
    events = build_activity_events([dup, dict(dup)])

    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == "completion:synth_0001"
    assert ev["runId"] == "synth_0001"
    assert ev["status"] == "ok"
