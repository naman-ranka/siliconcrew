"""Stage visibility through the unified status payload (Wave 9).

get_stage_status was deleted: its content (per-stage table + file-derived
history) lives on get_synthesis_status(run_id) as ``stages`` /
``stage_history`` / ``current_stage``. Same scenarios as before: the fixture
workspace's persisted stage table, max_stage-bounded runs (skipped stages),
and a live runtime job.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "stage_status_workspace")


def _runtime_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "manager_runtime_workspace")


def _reset_runtime_workspace(workspace: str) -> None:
    synth_runs = os.path.join(workspace, "synth_runs")
    os.makedirs(synth_runs, exist_ok=True)
    for name in os.listdir(synth_runs):
        path = os.path.join(synth_runs, name)
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass

    for name in [
        "counter_stage_status.v",
        "counter_stage_status_spec.yaml",
        "counter.v",
        "counter_spec.yaml",
        "constraints.sdc",
    ]:
        path = os.path.join(workspace, name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _wait_for_terminal(run_id: str, workspace: str) -> dict:
    for _ in range(60):
        status = sm.get_synthesis_status(run_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal status")


def test_status_payload_carries_persisted_stage_table():
    workspace = _fixture_workspace()
    result = sm.get_synthesis_status("synth_0001", workspace=workspace)

    assert result["run_id"] == "synth_0001"
    assert result["status"] == "completed"
    assert result["current_stage"] == "finish"
    assert result["stage"] == "finish"
    stage_statuses = {s: m.get("status") for s, m in result["stages"].items()}
    assert stage_statuses["finish"] == "completed"
    assert "failed" not in stage_statuses.values()
    assert "running" not in stage_statuses.values()
    # File-derived history is always present (this legacy fixture keeps no
    # artifact files, so it proves shape, not per-stage completion).
    assert [h["stage"] for h in result["stage_history"]] == sm.PD_STAGE_SEQUENCE


def test_status_derives_stage_history_for_legacy_meta_without_stages(tmp_path):
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0009")
    reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "legacy_top", "base")
    results = os.path.join(run_dir, "orfs_results", "sky130hd", "legacy_top", "base")
    os.makedirs(reports, exist_ok=True)
    os.makedirs(results, exist_ok=True)
    _write_file(os.path.join(workspace, "synth_runs", "LATEST"), "synth_0009")
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({"run_id": "synth_0009", "status": "completed", "top_module": "legacy_top", "platform": "sky130hd"}),
    )
    _write_file(os.path.join(reports, "6_finish.rpt"), "wns max 0.01\n")
    _write_file(os.path.join(results, "1_synth.odb"), "odb")
    _write_file(os.path.join(results, "6_final.v"), "module legacy_top(input clk, output y); endmodule")

    result = sm.get_synthesis_status("synth_0009", workspace=workspace)

    assert result["status"] == "completed"
    # No persisted stage table — the FILE trail still proves stage completion.
    history = {h["stage"]: h["status"] for h in result["stage_history"]}
    assert history["synth"] == "completed"
    assert history["finish"] == "completed"
    # Completed full-flow run reports its bound as the stage.
    assert result["stage"] == "finish"


def test_bounded_run_reports_skipped_stages_beyond_max_stage(tmp_path):
    """max_stage bounds the plan: stages past the bound are 'skipped', the
    completed run sits AT its bound."""
    workspace = str(tmp_path)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
    os.makedirs(results, exist_ok=True)
    dispatched = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    _write_file(os.path.join(run_dir, "constraints.sdc"), "create_clock\n")
    _write_file(os.path.join(results, "1_synth.odb"), "odb")
    _write_file(os.path.join(results, "2_floorplan.odb"), "odb")
    _write_file(os.path.join(results, "3_place.odb"), "odb")
    stages = sm._init_stage_metadata()
    for s in ["constraints", "synth", "floorplan", "place"]:
        stages[s]["status"] = "completed"
    for s in ["cts", "grt", "route", "finish"]:
        stages[s]["status"] = "skipped"
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": "synth_0001",
            "status": "completed",
            "max_stage": "place",
            "current_stage": "place",
            "dispatched_at": dispatched,
            "top_module": "counter",
            "platform": "sky130hd",
            "stages": stages,
        }),
    )

    result = sm.get_synthesis_status("synth_0001", workspace=workspace)

    assert result["status"] == "completed"
    assert result["stage"] == "place"
    assert result["current_stage"] == "place"
    history = {h["stage"]: h["status"] for h in result["stage_history"]}
    assert history["constraints"] == "completed"
    assert history["synth"] == "completed"
    assert history["floorplan"] == "completed"
    assert history["place"] == "completed"
    for s in ["cts", "grt", "route", "finish"]:
        assert history[s] == "skipped", s
    skipped = {s for s, m in result["stages"].items() if m.get("status") == "skipped"}
    assert skipped == {"cts", "grt", "route", "finish"}


def test_stage_fields_from_runtime_job(monkeypatch):
    workspace = _runtime_workspace()
    _reset_runtime_workspace(workspace)
    design = os.path.join(workspace, "counter_stage_status.v")
    _write_file(
        design,
        "module counter_stage_status(input clk, output reg q); always @(posedge clk) q<=~q; endmodule",
    )
    spec = DesignSpec(
        module_name="counter_stage_status",
        description="status",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_stage_status_spec.yaml"))

    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter_stage_status", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter_stage_status", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        _write_file(os.path.join(reports, "6_finish.rpt"), "wns max 0.01\n")
        _write_file(os.path.join(results, "6_final.v"), "module counter_stage_status(input clk, output q); endmodule")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs", fake_orfs)
    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter_stage_status",
        platform="sky130hd",
    )
    _wait_for_terminal(started["run_id"], workspace)

    result = sm.get_synthesis_status(started["run_id"], workspace=workspace)
    assert result["run_id"] == started["run_id"]
    assert result["status"] == "completed"
    assert result["current_stage"] == "finish"
    history = {h["stage"]: h["status"] for h in result["stage_history"]}
    assert history["constraints"] == "completed"  # this run wrote constraints.sdc post-dispatch
    assert history["finish"] == "completed"
