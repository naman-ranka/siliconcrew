import json
import os
import shutil
import time

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "manager_runtime_workspace")


def _reset_workspace(workspace: str) -> None:
    synth_runs = os.path.join(workspace, "synth_runs")
    os.makedirs(synth_runs, exist_ok=True)
    for name in os.listdir(synth_runs):
        path = os.path.join(synth_runs, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass

    for name in ["counter.v", "counter_spec.yaml", "constraints.sdc"]:
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


def test_stage_metadata_runtime_records_completed_stages(monkeypatch):
    workspace = _fixture_workspace()
    _reset_workspace(workspace)

    design = os.path.join(workspace, "counter.v")
    _write_file(
        design,
        "module counter(input clk, input rst, output reg [3:0] q); always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule",
    )
    spec = DesignSpec(
        module_name="counter",
        description="counter",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))

    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
        logs = os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        os.makedirs(logs, exist_ok=True)
        _write_file(os.path.join(reports, "2_floorplan_final.rpt"), "floorplan\n")
        _write_file(os.path.join(logs, "3_3_place_gp.json"), "{\"stage\":\"place\"}")
        _write_file(os.path.join(reports, "4_cts_final.rpt"), "cts\n")
        _write_file(os.path.join(logs, "5_1_grt.log"), "[INFO GRT-0096] Final congestion report:\nTotal 10 2 20.0% 0 / 0 / 0\n")
        _write_file(os.path.join(reports, "5_route_drc.rpt"), "")
        _write_file(os.path.join(reports, "6_finish.rpt"), "wns max 0.12\n")
        _write_file(os.path.join(results, "2_floorplan.odb"), "")
        _write_file(os.path.join(results, "3_place.odb"), "")
        _write_file(os.path.join(results, "4_cts.odb"), "")
        _write_file(os.path.join(results, "5_1_grt.odb"), "")
        _write_file(os.path.join(results, "5_route.odb"), "")
        _write_file(os.path.join(results, "6_final.v"), "module counter(input clk,input rst,output [3:0] q);endmodule")
        _write_file(os.path.join(results, "6_final.sdc"), "create_clock -period 10 [get_ports clk]")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter",
        platform="sky130hd",
    )
    final = _wait_for_terminal(started["job_id"], workspace)

    assert final["status"] == "completed"
    assert final["current_stage"] == "finish"
    assert final["stages"]["constraints"]["status"] == "completed"
    assert final["stages"]["floorplan"]["status"] == "completed"
    assert final["stages"]["place"]["status"] == "completed"
    assert final["stages"]["cts"]["status"] == "completed"
    assert final["stages"]["grt"]["status"] == "completed"
    assert final["stages"]["route"]["status"] == "completed"
    assert final["stages"]["finish"]["status"] == "completed"
    assert final["stages"]["finish"]["artifacts"]["netlist"].endswith("6_final.v")

    run_meta = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(run_meta, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["current_stage"] == "finish"
    assert data["stages"]["cts"]["artifacts"]["report"].endswith("4_cts_final.rpt")
    assert data["stages"]["grt"]["artifacts"]["log"].endswith("5_1_grt.log")
