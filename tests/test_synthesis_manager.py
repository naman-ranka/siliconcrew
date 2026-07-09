import json
import os
import tempfile
import time

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_start_and_poll_synthesis_job_with_guardrails(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
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
            os.makedirs(os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base"), exist_ok=True)
            os.makedirs(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base"), exist_ok=True)
            report = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "2_1_floorplan.rpt")
            netlist = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "6_final.v")
            with open(report, "w", encoding="utf-8") as f:
                f.write("Chip area for module 'counter': 12.34\nNumber of cells: 9\nwns 0.12\n")
            with open(netlist, "w", encoding="utf-8") as f:
                f.write("module counter(input clk,input rst,output [3:0] q);endmodule")
            return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)
        monkeypatch.setattr(sm, "_run_equiv_check", lambda *a, **k: {"status": "pass", "note": "ok"})

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="sky130hd",
            run_equiv=True,
        )

        # One key: run_id. No process-lifetime job_id anymore (Wave 9).
        assert "job_id" not in started
        assert started["run_id"] == "synth_0001"
        assert started["status"] == "queued"
        assert started["timeout_sec"] > 0
        assert started["poll_after_sec"] > 0

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "completed"
        assert final["auto_checks"]["constraints"] == "pass"
        assert final["auto_checks"]["signoff"] == "pass"
        assert final["auto_checks"]["equiv"] == "pass"

        run_meta = os.path.join(workspace, "synth_runs", "synth_0001", "run_meta.json")
        assert os.path.exists(run_meta)
        data = json.loads(open(run_meta, "r", encoding="utf-8").read())
        assert data["platform"] == "sky130hd"
        assert data["netlist_path"].endswith("6_final.v")


def test_constraints_guardrail_blocks_unsafe_success(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = os.path.join(workspace, "counter.v")
        _write_file(design, "module counter(input clk, output y); assign y=clk; endmodule")

        # Intentionally mismatch spec module name
        spec = DesignSpec(
            module_name="other_top",
            description="bad",
            clock_period_ns=10.0,
            ports=[PortSpec(name="clk", direction="input")],
        )
        save_yaml_file(spec, os.path.join(workspace, "other_top_spec.yaml"))

        called = {"value": False}

        def fake_orfs(**kwargs):
            called["value"] = True
            return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="sky130hd",
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "failed"
        assert final["auto_checks"]["constraints"] == "fail"
        assert called["value"] is False


def test_explicit_clock_overrides_spec_clock(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
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

        seen = {}

        def fake_orfs(**kwargs):
            seen["clock_period_ns"] = kwargs["clock_period_ns"]
            run_dir = kwargs["run_dir"]
            os.makedirs(os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base"), exist_ok=True)
            os.makedirs(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base"), exist_ok=True)
            with open(os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "x.rpt"), "w", encoding="utf-8") as f:
                f.write("Chip area for module 'counter': 5.0\n")
            with open(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "6_final.v"), "w", encoding="utf-8") as f:
                f.write("module counter(input clk,input rst,output [3:0] q);endmodule")
            return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="sky130hd",
            clock_period_ns=3.5,
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "completed"
        assert seen["clock_period_ns"] == 3.5

        run_meta = os.path.join(workspace, "synth_runs", "synth_0001", "run_meta.json")
        data = json.loads(open(run_meta, "r", encoding="utf-8").read())
        assert data["requested_clock_period_ns"] == 3.5
        assert data["effective_clock_period_ns"] == 3.5
        assert data["clock_period_ns"] == 3.5
        assert data["clock_source"] == "requested"


def test_constraints_guardrail_allows_combinational_default_clock(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = os.path.join(workspace, "and2.v")
        _write_file(design, "module and2(input a, input b, output y); assign y=a&b; endmodule")

        spec = DesignSpec(
            module_name="and2",
            description="and gate",
            clock_period_ns=10.0,
            ports=[
                PortSpec(name="a", direction="input"),
                PortSpec(name="b", direction="input"),
                PortSpec(name="y", direction="output"),
            ],
        )
        save_yaml_file(spec, os.path.join(workspace, "and2_spec.yaml"))

        def fake_orfs(**kwargs):
            run_dir = kwargs["run_dir"]
            os.makedirs(os.path.join(run_dir, "orfs_reports", "sky130hd", "and2", "base"), exist_ok=True)
            os.makedirs(os.path.join(run_dir, "orfs_results", "sky130hd", "and2", "base"), exist_ok=True)
            with open(os.path.join(run_dir, "orfs_reports", "sky130hd", "and2", "base", "x.rpt"), "w", encoding="utf-8") as f:
                f.write("Chip area for module 'and2': 1.0\n")
            with open(os.path.join(run_dir, "orfs_results", "sky130hd", "and2", "base", "6_final.v"), "w", encoding="utf-8") as f:
                f.write("module and2(input a,input b,output y); assign y=a&b; endmodule")
            return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="and2",
            constraints_mode="auto",
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "completed"
        assert final["auto_checks"]["constraints"] == "pass"
        assert "default clock fallback" in final["check_notes"].lower() or "all guardrails passed" in final["check_notes"].lower()


def test_constraints_guardrail_strict_can_fail_on_missing_clock(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = os.path.join(workspace, "and2.v")
        _write_file(design, "module and2(input a, input b, output y); assign y=a&b; endmodule")

        spec = DesignSpec(
            module_name="and2",
            description="and gate",
            clock_period_ns=10.0,
            ports=[
                PortSpec(name="a", direction="input"),
                PortSpec(name="b", direction="input"),
                PortSpec(name="y", direction="output"),
            ],
        )
        save_yaml_file(spec, os.path.join(workspace, "and2_spec.yaml"))

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="and2",
            constraints_mode="strict",
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "failed"
        assert final["auto_checks"]["constraints"] == "fail"
        assert "constraints_mode='auto'" in final["check_notes"] or "constraints_mode='bypass'" in final["check_notes"]


def _write_clean_final_orfs_outputs(run_dir: str, top_module: str, dirty_route_drc: bool = False) -> None:
    report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", top_module, "base")
    result_dir = os.path.join(run_dir, "orfs_results", "sky130hd", top_module, "base")
    log_dir = os.path.join(run_dir, "orfs_logs", "sky130hd", top_module, "base")
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    _write_file(
        os.path.join(report_dir, "6_finish.rpt"),
        "wns max 0.3391\n"
        "tns max 0.0000\n"
        "setup violation count 0\n"
        "hold violation count 0\n"
        "max slew violation count 0\n"
        "max cap violation count 0\n"
        "max fanout violation count 0\n"
        "Total  1.23e-04  2.34e-05  1.11e-06  4.27e-02  100.0%\n",
    )
    _write_file(
        os.path.join(report_dir, "synth_stat.txt"),
        f"Chip area for module '\\{top_module}': 123.45\n814 7.33E+03 cells\n",
    )
    _write_file(
        os.path.join(report_dir, "5_route_drc.rpt"),
        "short violation\n" if dirty_route_drc else "",
    )
    _write_file(
        os.path.join(result_dir, "6_final.v"),
        f"module {top_module}(input clk, input rst, output [3:0] q); endmodule\n",
    )
    _write_file(os.path.join(result_dir, "6_final.gds"), "fake-gds\n")
    _write_file(os.path.join(log_dir, "6_report.json"), json.dumps({"finish__flow__errors__count": 0}))


def test_nonzero_orfs_exit_with_clean_final_artifacts_completes(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
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
            _write_clean_final_orfs_outputs(kwargs["run_dir"], "counter")
            return {"success": False, "stdout": "nonzero docker exit", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="sky130hd",
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "completed"
        assert final["auto_checks"]["signoff"] == "pass"
        assert final["summary_metrics"]["wns_ns"] == 0.3391
        assert "ORFS command returned nonzero" in final["check_notes"]

        run_meta = os.path.join(workspace, "synth_runs", "synth_0001", "run_meta.json")
        data = json.loads(open(run_meta, "r", encoding="utf-8").read())
        assert data["docker_success"] is False
        assert data["status"] == "completed"


def test_nonzero_orfs_exit_with_dirty_final_artifacts_fails(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
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
            _write_clean_final_orfs_outputs(kwargs["run_dir"], "counter", dirty_route_drc=True)
            return {"success": False, "stdout": "nonzero docker exit", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="sky130hd",
        )

        final = None
        for _ in range(40):
            status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            if status["status"] in {"completed", "failed"}:
                final = status
                break
            time.sleep(0.05)

        assert final is not None
        assert final["status"] == "failed"
        assert final["auto_checks"]["signoff"] == "fail"
        assert "final route DRC report is not empty" in final["check_notes"]


def test_disk_recovery_and_poll_guidance():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        os.makedirs(run_dir, exist_ok=True)

        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "run_id": "synth_0001",
                    "status": "completed",
                    "auto_checks": {"constraints": "pass", "signoff": "pass", "equiv": "skip"},
                    "check_notes": "Recovered complete",
                    "summary_metrics": {"area_um2": 3.14},
                },
                f,
                indent=2,
            )

        # Old dirs may still carry a legacy "jobs" mapping — tolerated on read,
        # never consulted: recovery keys on run_id alone.
        with open(os.path.join(workspace, "synth_runs", "index.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "runs": [{"run_id": "synth_0001", "status": "completed", "updated_at": "x"}],
                    "jobs": [{"job_id": "job_legacy_1", "run_id": "synth_0001", "status": "completed", "updated_at": "x"}],
                },
                f,
                indent=2,
            )

        recovered = sm.get_synthesis_status("synth_0001", workspace=workspace)
        assert recovered["status"] == "completed"
        assert recovered["recovered_from_index"] is True
        assert recovered["poll_after_sec"] == 0


def test_poll_rate_limit_on_running_jobs(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = os.path.join(workspace, "counter.v")
        _write_file(design, "module counter(input clk, input rst, output reg [3:0] q); always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule")

        spec = DesignSpec(
            module_name="counter",
            description="counter",
            clock_period_ns=10.0,
            ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
        )
        save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))

        original_interval = sm.POLL_MIN_INTERVAL_SEC
        sm.POLL_MIN_INTERVAL_SEC = 5.0

        def fake_orfs(**kwargs):
            # Keep the worker in running state for a short duration.
            time.sleep(0.3)
            run_dir = kwargs["run_dir"]
            os.makedirs(os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base"), exist_ok=True)
            os.makedirs(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base"), exist_ok=True)
            with open(os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "x.rpt"), "w", encoding="utf-8") as f:
                f.write("Chip area for module 'counter': 5.0\n")
            with open(os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "6_final.v"), "w", encoding="utf-8") as f:
                f.write("module counter(input clk,input rst,output [3:0] q);endmodule")
            return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs", fake_orfs)

        try:
            started = sm.start_synthesis_job(
                workspace=workspace,
                verilog_files=[design],
                top_module="counter",
                platform="sky130hd",
            )

            first = sm.get_synthesis_status(started["run_id"], workspace=workspace)
            second = sm.get_synthesis_status(started["run_id"], workspace=workspace)

            # Immediate second poll should be throttled while still running/queued.
            if first["status"] in {"running", "queued"}:
                assert second.get("rate_limited") is True
                assert second.get("retry_after_sec", 0) > 0
            else:
                # Job can complete very quickly in some environments.
                assert second["status"] in {"completed", "failed"}

            # Ensure worker is finished before tempdir cleanup on Windows.
            for _ in range(120):
                final = sm.get_synthesis_status(started["run_id"], workspace=workspace)
                if final["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
        finally:
            sm.POLL_MIN_INTERVAL_SEC = original_interval
