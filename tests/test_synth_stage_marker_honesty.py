"""A bounded synth run whose synth stage failed must not report "completed".

yosys writes synth_stat.txt before synth_odb.tcl reads the netlist back into
OpenROAD. When that read fails (seen on the pinned ORFS image for any design
with a `signed` port: STA-0171 syntax error), the stat report exists, no
1_synth.odb does, and the flow exits non-zero. The run used to report
"completed" off the stat report alone. Found by the overnight run of
2026-09-23 (L4B MAC, then a minimal signed-port repro).
"""
import os
import tempfile
import time

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _counter_workspace(workspace: str) -> str:
    design = os.path.join(workspace, "counter.v")
    _write_file(
        design,
        "module counter(input clk, input rst, output reg [3:0] q);"
        " always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule",
    )
    spec = DesignSpec(
        module_name="counter",
        description="counter",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))
    return design


def _run_to_completion(workspace: str, **kwargs) -> dict:
    started = sm.start_synthesis_job(workspace=workspace, **kwargs)
    for _ in range(60):
        status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("run never reached a terminal state")


def test_synth_that_failed_at_the_netlist_read_is_failed(monkeypatch):
    def synth_fails_after_stat(**kwargs):
        # What the pinned image leaves behind: the stat report, no checkpoint.
        _write_file(
            os.path.join(kwargs["run_dir"], "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
            "Chip area for module '\\counter': 12.0\n10 1.0 cells\n",
        )
        return {"success": False, "stdout": "",
                "stderr": "[ERROR STA-0171] ./results/sky130hd/counter/base/1_2_yosys.v line 11, syntax error",
                "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs_targets", synth_fails_after_stat)
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        final = _run_to_completion(workspace, verilog_files=[design], top_module="counter", max_stage="synth")

    assert final["status"] == "failed"


def test_stat_report_alone_does_not_prove_synth_completed(tmp_path):
    run_dir = str(tmp_path)
    _write_file(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
        "Chip area for module '\\counter': 12.0\n10 1.0 cells\n",
    )
    assert sm._find_stage_completion_marker(run_dir, "synth") is None

    _write_file(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.odb"), "odb")
    assert sm._find_stage_completion_marker(run_dir, "synth").endswith("1_synth.odb")
