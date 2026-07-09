"""Read-time reconciliation of a synthesis run stuck at a non-terminal status.

On serverless (Cloud Run) the worker that writes the terminal status can be
killed after the HTTP response returns, leaving run_meta at "running" even though
ORFS finished and its artifacts synced. _reconcile_stale_status adopts
"completed" ONLY when the finish-stage report (6_finish.rpt) is present — the one
artifact that proves the full flow finished. synth_stat.txt (area/cells) alone is
NOT enough (a run that failed after logic synthesis has it too), so a failed run
must not be mis-marked as completed.

Wave 9 adds the death verdict: running + no live future + past
dispatched_at + timeout_sec + STALE_RUN_GRACE_SEC with no file activity →
failed ("orchestrator lost"), announced exactly once via the completion.event
marker + a deterministic-id activity record.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from src.tools import synthesis_manager as sm
from src.utils.attempt_logger import EVENTS_FILE


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _age_files(root: str, seconds_ago: float) -> None:
    """Explicit old mtimes (no sleeping): everything under root looks idle."""
    import time as _time

    ts = _time.time() - seconds_ago
    for r, _dirs, files in os.walk(root):
        for name in files:
            os.utime(os.path.join(r, name), (ts, ts))


def test_reconciles_when_finish_report_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_find_report_file",
                        lambda rd, name: os.path.join(rd, name) if name == "6_finish.rpt" else None)
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": 337.8, "cell_count": 43})
    meta = {"status": "running", "run_id": "synth_0001"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "completed"
    assert out["summary_metrics"]["area_um2"] == 337.8
    assert out["finished_at"]
    assert os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_does_not_mark_completed_on_synth_stat_alone(tmp_path, monkeypatch):
    """Regression: a run that reached logic synthesis (area/cells) but failed
    before finish (no 6_finish.rpt) must NOT be reported as completed."""
    monkeypatch.setattr(sm, "_find_report_file", lambda rd, name: None)  # no finish report
    # Even if metrics would parse, absence of the finish report must win.
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": 337.8, "cell_count": 43})
    meta = {"status": "running"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_does_not_touch_already_terminal_runs(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _spy(rd, name):
        calls["n"] += 1
        return os.path.join(rd, name)

    monkeypatch.setattr(sm, "_find_report_file", _spy)

    for status in ("completed", "failed"):
        out = sm._reconcile_stale_status(str(tmp_path), {"status": status})
        assert out["status"] == status

    assert calls["n"] == 0  # short-circuits before touching disk


# --------------------------------------------------------------------------
# Death verdict (Wave 9): no run is ever stuck at "running"
# --------------------------------------------------------------------------


def _make_stale_run(tmp_path, run_id="synth_0001", dispatched_ago=2000.0, timeout_sec=600):
    """Workspace with one silent running run: past its ceiling, files idle."""
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    logs = os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "1_1_yosys.log"), "w", encoding="utf-8") as f:
        f.write("yosys started\n")
    meta = {
        "run_id": run_id,
        "status": "running",
        "dispatched_at": _iso_ago(dispatched_ago),
        "timeout_sec": timeout_sec,
        "top_module": "counter",
        "platform": "sky130hd",
    }
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _age_files(run_dir, dispatched_ago)  # idle since dispatch — liveness cold
    return workspace, run_dir, meta


def test_death_verdict_tombstones_expired_silent_run(tmp_path):
    workspace, run_dir, meta = _make_stale_run(tmp_path)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "failed"
    assert "orchestrator lost" in out["check_notes"]
    assert out["finished_at"]
    # Tombstone persisted durably — any later reader sees terminal state.
    with open(os.path.join(run_dir, sm.RUN_META_FILENAME), "r", encoding="utf-8") as f:
        persisted = json.load(f)
    assert persisted["status"] == "failed"
    # Completion announced: O_EXCL marker + one system activity record.
    assert os.path.exists(os.path.join(run_dir, "completion.event"))
    from src.utils.attempt_logger import _read_events
    records = _read_events(os.path.join(workspace, EVENTS_FILE))
    completions = [r for r in records if r.get("tool_call_id") == "completion:synth_0001"]
    assert len(completions) == 1
    assert completions[0]["event_type"] == "tool_result"
    assert completions[0]["source"] == "system"
    assert completions[0]["tool"] == "synthesis_run"
    assert completions[0]["arguments"] == {"run_id": "synth_0001"}


def test_death_verdict_emits_completion_event_exactly_once(tmp_path):
    workspace, run_dir, meta = _make_stale_run(tmp_path)

    first = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)
    assert first["status"] == "failed"
    # A racing second reader that also reached the terminal transition tries
    # to announce too — the O_EXCL marker claim makes it a no-op.
    sm._emit_completion_event(workspace, run_dir, "synth_0001", first)
    # And a reader that re-reads the persisted tombstone short-circuits.
    second = sm._reconcile_stale_status(
        run_dir, sm._read_run_meta(run_dir), workspace=workspace, has_live_future=False
    )
    assert second["status"] == "failed"

    from src.utils.attempt_logger import _read_events
    records = _read_events(os.path.join(workspace, EVENTS_FILE))
    completions = [r for r in records if r.get("tool_call_id") == "completion:synth_0001"]
    assert len(completions) == 1


def test_fresh_run_within_ceiling_left_running(tmp_path):
    workspace, run_dir, meta = _make_stale_run(tmp_path, dispatched_ago=10.0, timeout_sec=600)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


def test_live_future_trusted_over_ceiling(tmp_path):
    """This process owns the run — the worker writes the tombstone, not us."""
    workspace, run_dir, meta = _make_stale_run(tmp_path)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=True)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


def test_growing_files_keep_expired_run_alive(tmp_path):
    """local_docker heartbeat: logs still moving → the run is alive even past
    the ceiling (docker may outlive the orchestrator process)."""
    workspace, run_dir, meta = _make_stale_run(tmp_path)
    # One log line written "just now".
    fresh_log = os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base", "2_1_floorplan.log")
    with open(fresh_log, "w", encoding="utf-8") as f:
        f.write("floorplanning...\n")

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "running"


def test_legacy_meta_without_timestamps_is_never_tombstoned(tmp_path):
    """Guard: a legacy run with neither dispatched_at nor created_at has no
    honest ceiling — it is left untouched, never guessed dead."""
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)
    meta = {"run_id": "synth_0001", "status": "running"}
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _age_files(run_dir, 10_000.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))
    # And through the public read: still running, not failed/unknown.
    status = sm.get_synthesis_status("synth_0001", workspace=workspace)
    assert status["status"] == "running"


def test_completed_leg_unchanged_and_announced(tmp_path):
    """Artifact adoption (the pre-Wave-9 leg) still wins over the death
    verdict, and now announces completion exactly once too."""
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
    os.makedirs(results, exist_ok=True)
    with open(os.path.join(results, "1_synth.odb"), "w", encoding="utf-8") as f:
        f.write("odb")
    meta = {
        "run_id": "synth_0001",
        "status": "running",
        "max_stage": "synth",
        "dispatched_at": _iso_ago(5000.0),  # ceiling long past — artifacts still win
        "timeout_sec": 600,
    }
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _age_files(run_dir, 5000.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "completed"
    assert os.path.exists(os.path.join(run_dir, "completion.event"))
    from src.utils.attempt_logger import _read_events
    records = _read_events(os.path.join(workspace, EVENTS_FILE))
    completions = [r for r in records if r.get("tool_call_id") == "completion:synth_0001"]
    assert len(completions) == 1
    assert completions[0]["status"] == "success"
