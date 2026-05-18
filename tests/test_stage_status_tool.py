import json
import os
import time

from src.tools import synthesis_manager as sm
from src.tools.synthesis_manager import get_stage_status
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "stage_status_workspace")


def _runtime_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "manager_runtime_workspace")


def _reset_runtime_workspace(workspace: str) -> None:
    synth_runs = os.path.join(workspace, "synth_runs")
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
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _wait_for_terminal(job_id: str, workspace: str) -> dict:
    for _ in range(60):
        status = sm.get_synthesis_job_status(job_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal status")


def test_get_stage_status_reads_stage_metadata():
    workspace = _fixture_workspace()
    result = get_stage_status(workspace=workspace, run_id="synth_0001")

    assert result["status"] == "ok"
    assert result["run_status"] == "completed"
    assert result["current_stage"] == "finish"
    assert "finish" in result["completed_stages"]
    assert result["failed_stages"] == []
    assert result["running_stages"] == []


def test_get_stage_status_from_runtime_job(monkeypatch):
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
    _wait_for_terminal(started["job_id"], workspace)

    result = get_stage_status(workspace=workspace, run_id=started["run_id"])
    assert result["status"] == "ok"
    assert result["run_id"] == started["run_id"]
    assert result["current_stage"] == "finish"
    assert result["run_status"] == "completed"
