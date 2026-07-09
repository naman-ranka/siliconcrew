"""Wave 9 adversarial-review regression tests (findings F1-F3, F5-F8).

F1  stage_progress_from_files mtime floor is timezone-independent (naive
    dispatched_at is assumed UTC; never interpreted in the host TZ).
F2  _JOBS/_POLL_CACHE/_POLL_BACKOFF_STATE are keyed workspace::run_id — two
    workspaces' synth_0001 never clobber each other in one process.
F3  _reconcile_stale_status trusts a live worker FIRST: neither the
    completed-marker leg nor the death leg fires under a live future.
F5  POST /runs/{id}/retry maps a validation "error" result to HTTP 400.
F6  Death-verdict deadline is based on worker start (created_at); a still
    queued run gets a full extra timeout for legitimate queue backlog.
F7  stage_progress_from_files honors retry_start_stage: pre-retry stages
    render "inherited" and are never picked as `current`.
F8  _wait_for_synthesis_job takes one final status sample after the wait
    loop so a run that finished during the last sleep is not reported as
    timed_out/running.
"""
import contextlib
import json
import os
import time
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

import pytest

from src.tools import synthesis_manager as sm
from src.tools import wrappers


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _write(path: str, content: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _age_files(root: str, seconds_ago: float) -> None:
    ts = time.time() - seconds_ago
    for r, _dirs, files in os.walk(root):
        for name in files:
            os.utime(os.path.join(r, name), (ts, ts))


class HeldExecutor:
    """Accepts submissions but never runs them — the run stays queued."""

    def __init__(self):
        self.pending = []

    def submit(self, fn, *args):
        f: Future = Future()
        self.pending.append((f, fn, args))
        return f


# --------------------------------------------------------------------------
# F1: mtime floor must not depend on the host timezone
# --------------------------------------------------------------------------


@contextlib.contextmanager
def _host_tz(tzname: str):
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset unavailable on this platform")
    old = os.environ.get("TZ")
    os.environ["TZ"] = tzname
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def _mid_flow_run(run_dir: str) -> None:
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.odb"), "odb")


@pytest.mark.parametrize("aware", [True, False], ids=["tz-aware", "naive-utc"])
def test_floor_fresh_markers_stay_completed_west_of_utc(tmp_path, aware):
    """Under TZ=America/New_York (UTC-4 in July) the pre-fix naive
    .timestamp() floor lands HOURS in the future, mislabeling this run's own
    fresh markers as 'inherited'."""
    run_dir = str(tmp_path)
    _mid_flow_run(run_dir)  # markers written "now"
    dispatched = datetime.now(timezone.utc) - timedelta(seconds=60)
    value = dispatched.isoformat() if aware else dispatched.replace(tzinfo=None).isoformat()
    meta = {"status": "running", "max_stage": "finish", "dispatched_at": value}

    with _host_tz("America/New_York"):
        out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "completed"
    assert history["synth"] == "completed"
    assert out["current_stage"] == "floorplan"


@pytest.mark.parametrize("aware", [True, False], ids=["tz-aware", "naive-utc"])
def test_floor_parent_checkpoints_stay_inherited_east_of_utc(tmp_path, aware):
    """Under TZ=Asia/Tokyo (UTC+9) the pre-fix floor lands hours in the past,
    adopting the parent's pre-dispatch checkpoints as this run's own work."""
    run_dir = str(tmp_path)
    _mid_flow_run(run_dir)
    dispatched_ts = time.time() - 60.0
    old = dispatched_ts - 3600.0  # copied-in parent artifacts, 1h pre-dispatch
    os.utime(os.path.join(run_dir, "constraints.sdc"), (old, old))
    os.utime(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.odb"), (old, old))
    dispatched = datetime.fromtimestamp(dispatched_ts, tz=timezone.utc)
    value = dispatched.isoformat() if aware else dispatched.replace(tzinfo=None).isoformat()
    meta = {"status": "running", "max_stage": "finish", "dispatched_at": value}

    with _host_tz("Asia/Tokyo"):
        out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "inherited"
    assert history["synth"] == "inherited"


# --------------------------------------------------------------------------
# F2: workspace-scoped in-memory bookkeeping
# --------------------------------------------------------------------------


def test_same_run_id_in_two_workspaces_never_clobbers(tmp_path):
    ws_a = str(tmp_path / "tenant_a")
    ws_b = str(tmp_path / "tenant_b")
    executor = HeldExecutor()
    sm.set_job_executor(executor)
    try:
        a = sm.start_synthesis_job(workspace=ws_a, verilog_files=["a.v"], top_module="top_a")
        b = sm.start_synthesis_job(workspace=ws_b, verilog_files=["b.v"], top_module="top_b")
        assert a["run_id"] == b["run_id"] == "synth_0001"

        # Distinct scoped slots — neither dispatch overwrote the other.
        assert sm._job_key(ws_a, "synth_0001") in sm._JOBS
        assert sm._job_key(ws_b, "synth_0001") in sm._JOBS

        status_a = sm.get_synthesis_status("synth_0001", workspace=ws_a)
        status_b = sm.get_synthesis_status("synth_0001", workspace=ws_b)
        assert status_a["top_module"] == "top_a"
        assert status_b["top_module"] == "top_b"
        # B's first poll right after A's must NOT be served (rate-limited)
        # from A's cache entry.
        assert status_b.get("rate_limited") is not True

        # The poll cache stays per-workspace too: an immediate re-poll of A is
        # rate-limited with A'S OWN payload, and never leaks into B's slot.
        again_a = sm.get_synthesis_status("synth_0001", workspace=ws_a)
        assert again_a.get("rate_limited") is True
        assert again_a["top_module"] == "top_a"
        assert sm._job_key(ws_a, "synth_0001") in sm._POLL_CACHE
        assert sm._job_key(ws_b, "synth_0001") in sm._POLL_CACHE
    finally:
        sm.set_job_executor(None)


def test_live_job_elsewhere_does_not_shadow_disk_meta_of_other_workspace(tmp_path):
    """The scoped key preserves the old cross-workspace guard: workspace B's
    on-disk synth_0001 answers from disk even while THIS process holds a live
    future for workspace A's synth_0001."""
    ws_a = str(tmp_path / "tenant_a")
    ws_b = str(tmp_path / "tenant_b")
    run_dir_b = os.path.join(ws_b, "synth_runs", "synth_0001")
    _write(os.path.join(run_dir_b, "run_meta.json"), json.dumps({
        "run_id": "synth_0001", "status": "completed", "top_module": "top_b",
        "max_stage": "finish", "current_stage": "finish",
    }))

    executor = HeldExecutor()
    sm.set_job_executor(executor)
    try:
        sm.start_synthesis_job(workspace=ws_a, verilog_files=["a.v"], top_module="top_a")
        status_b = sm.get_synthesis_status("synth_0001", workspace=ws_b)
        assert status_b["status"] == "completed"
        assert status_b["top_module"] == "top_b"
        assert status_b["recovered_from_index"] is True
    finally:
        sm.set_job_executor(None)


# --------------------------------------------------------------------------
# F3: a live worker's verdict beats the completed-marker leg
# --------------------------------------------------------------------------


def _synth_bounded_run(workspace: str, run_id: str = "synth_0001") -> tuple:
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    _write(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
        "Chip area for module '\\counter': 12.0\n10 1.0 cells\n",
    )
    meta = {"run_id": run_id, "status": "running", "max_stage": "synth"}
    return run_dir, meta


def test_reconciler_never_completes_under_explicit_live_future(tmp_path):
    """Target-stage marker present, but the worker is still alive (it may yet
    fail signoff/equiv): meta must come back untouched."""
    workspace = str(tmp_path)
    run_dir, meta = _synth_bounded_run(workspace)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=True)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, sm.RUN_META_FILENAME))
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


def test_reconciler_resolves_live_future_from_workspace_scoped_jobs(tmp_path):
    """has_live_future=None path: the reconciler looks up _JOBS by the
    workspace-scoped key and trusts a not-done future; once the future is
    done the marker leg proceeds."""
    workspace = str(tmp_path)
    run_dir, meta = _synth_bounded_run(workspace)
    future: Future = Future()  # not done
    sm._JOBS[sm._job_key(workspace, "synth_0001")] = {
        "future": future, "workspace": workspace, "run_dir": run_dir, "created_at": _iso_ago(0),
    }

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace)
    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))

    future.set_result({"status": "completed"})
    out2 = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace)
    assert out2["status"] == "completed"


# --------------------------------------------------------------------------
# F6: death-verdict deadline base = worker start; queued gets extra grace
# --------------------------------------------------------------------------


def _silent_run(tmp_path, status="running", dispatched_ago=2000.0, created_ago=None, timeout_sec=600):
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    _write(os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base", "1_1_yosys.log"), "yosys\n")
    meta = {
        "run_id": "synth_0001",
        "status": status,
        "dispatched_at": _iso_ago(dispatched_ago),
        "timeout_sec": timeout_sec,
        "top_module": "counter",
        "platform": "sky130hd",
    }
    if created_ago is not None:
        meta["created_at"] = _iso_ago(created_ago)
    _write(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
    _age_files(run_dir, dispatched_ago)  # files idle — liveness cold
    return workspace, run_dir, meta


def test_queued_run_gets_a_full_extra_timeout_before_death(tmp_path):
    """Queue backlog is legitimate: dispatched+timeout+grace has passed but
    dispatched+2*timeout+grace has not — the queued run stays alive."""
    workspace, run_dir, meta = _silent_run(tmp_path, status="queued", dispatched_ago=800.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "queued"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


def test_queued_run_past_double_timeout_is_tombstoned(tmp_path):
    workspace, run_dir, meta = _silent_run(tmp_path, status="queued", dispatched_ago=1500.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "failed"
    assert "orchestrator lost" in out["check_notes"]


def test_running_deadline_counts_from_worker_start_not_dispatch(tmp_path):
    """A run that sat queued for a long time and whose worker started
    recently (created_at) is within its execution ceiling — queue wait must
    not eat into it."""
    workspace, run_dir, meta = _silent_run(tmp_path, dispatched_ago=2000.0, created_ago=100.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, "completion.event"))


def test_running_past_worker_start_ceiling_is_tombstoned(tmp_path):
    workspace, run_dir, meta = _silent_run(tmp_path, dispatched_ago=2000.0, created_ago=800.0)

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "failed"
    assert "orchestrator lost" in out["check_notes"]


def test_fresh_file_activity_still_keeps_expired_run_alive(tmp_path):
    """The file-activity heartbeat survives the F6 rework."""
    workspace, run_dir, meta = _silent_run(tmp_path, dispatched_ago=2000.0, created_ago=800.0)
    _write(os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base", "2_1_floorplan.log"), "fp\n")

    out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "running"


# --------------------------------------------------------------------------
# F7: retry_start_stage — earlier stages are inherited, never `current`
# --------------------------------------------------------------------------


def test_retry_without_markers_starts_current_at_retry_start_stage(tmp_path):
    """A just-dispatched place-retry has NO markers yet (hosted backends copy
    prerequisites remotely): constraints/synth/floorplan are the parent's,
    and `current` is the retry's actual first stage."""
    run_dir = str(tmp_path)
    meta = {
        "status": "running",
        "mode": "pd_retry",
        "retry_start_stage": "place",
        "retry_max_stage": "finish",
        "dispatched_at": _iso_ago(60.0),
    }

    out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "inherited"
    assert history["synth"] == "inherited"
    assert history["floorplan"] == "inherited"
    assert history["place"] == "running"
    assert out["current_stage"] == "place"


def test_retry_pre_start_stage_with_fresh_marker_still_completed(tmp_path):
    """A provably fresh (post-dispatch) marker on a pre-retry stage keeps
    counting as completed — only unproven stages fall back to inherited."""
    run_dir = str(tmp_path)
    _write(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "2_floorplan.odb"), "odb")
    meta = {
        "status": "running",
        "mode": "pd_retry",
        "retry_start_stage": "place",
        "retry_max_stage": "finish",
        "dispatched_at": _iso_ago(60.0),
    }

    out = sm.stage_progress_from_files(run_dir, meta)

    history = {h["stage"]: h["status"] for h in out["stage_history"]}
    assert history["constraints"] == "inherited"
    assert history["synth"] == "inherited"
    assert history["floorplan"] == "completed"
    assert out["current_stage"] == "place"


# --------------------------------------------------------------------------
# F8: final status sample after the wait loop
# --------------------------------------------------------------------------


def _fake_clock(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])

    def _sleep(seconds):
        clock["t"] += seconds

    monkeypatch.setattr(wrappers.time, "sleep", _sleep)
    return clock


def test_wait_takes_final_sample_and_catches_terminal_run(monkeypatch, tmp_path):
    clock = _fake_clock(monkeypatch)
    calls = {"n": 0}

    def _fake_status(run_id, workspace=None):
        calls["n"] += 1
        # Completes DURING the final sleep — only a post-loop sample sees it.
        if clock["t"] >= 5:
            return {"run_id": run_id, "status": "completed", "poll_after_sec": 0}
        return {"run_id": run_id, "status": "running", "poll_after_sec": 10}

    monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)

    out = wrappers._wait_for_synthesis_job(str(tmp_path), "synth_0001", 5, 2)

    assert out["status"] == "completed"
    assert out["timed_out"] is False
    assert calls["n"] == 2  # one in-loop sample + the final post-loop sample


def test_wait_final_sample_still_running_reports_timed_out(monkeypatch, tmp_path):
    _fake_clock(monkeypatch)

    def _fake_status(run_id, workspace=None):
        return {"run_id": run_id, "status": "running", "poll_after_sec": 10}

    monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)

    out = wrappers._wait_for_synthesis_job(str(tmp_path), "synth_0001", 5, 2)

    assert out["status"] == "running"
    assert out["timed_out"] is True
    assert "wait_for_synthesis" in out["next_action"] or "get_synthesis_status" in out["next_action"]


# --------------------------------------------------------------------------
# F5: REST retry endpoint surfaces validation errors as 400
# --------------------------------------------------------------------------


@pytest.fixture()
def rest_client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.actions import build_actions_router

    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    return TestClient(app), resolve("sess")


def test_rest_retry_surfaces_error_result_as_400(rest_client, monkeypatch):
    import src.api.actions as actions_mod

    client, _ws = rest_client

    def fake_retry(**kwargs):
        # Same rejected shape retry_pd_job returns for a bad stage.
        return {
            "status": "error",
            "message": f"Unsupported start_stage '{kwargs.get('start_stage')}'.",
            "supported_stages": sm.PD_RETRYABLE_STAGES,
        }

    monkeypatch.setattr(actions_mod, "retry_pd_job", fake_retry)

    r = client.post(
        "/api/workspace/sess/runs/synth_0001/retry",
        json={"fromStage": "bogus", "maxStage": "finish"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["ok"] is False
    assert detail["error"]["code"] == "invalid_request"
    assert "Unsupported start_stage" in detail["error"]["message"]


def test_rest_retry_dispatch_still_returns_ok(rest_client, monkeypatch):
    import src.api.actions as actions_mod

    client, _ws = rest_client
    monkeypatch.setattr(
        actions_mod, "retry_pd_job",
        lambda **kwargs: {"run_id": "synth_0002", "status": "queued", "poll_after_sec": 30},
    )

    r = client.post(
        "/api/workspace/sess/runs/synth_0001/retry",
        json={"fromStage": "floorplan", "maxStage": "finish"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["runId"] == "synth_0002"
