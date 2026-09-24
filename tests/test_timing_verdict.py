"""Wave C (sc#64 remainder): a real timing term in the guardrail summary.

The artifact/log guardrails could all pass on a design that closed nothing, so
the rollup had to say "timing not evaluated". Now it IS evaluated: setup slack
sign plus the setup/hold violation counts the finish parser already read and
threw away. It stays OUT of ``final_ok`` — a run that produced its GDS
*completed*; missing timing is a design verdict, not a flow failure.
"""
import json
import os
import tempfile
import time

import pytest

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


VIOLATING_FINISH = """\
Chip area for module 'counter': 12.34
Number of cells: 9
wns max -1137.0
tns max -9999.0
worst slack max -1137.59
clk period_min = 1147.59 fmax = 0.87
setup violation count 12
hold violation count 0
"""

MET_FINISH = """\
Chip area for module 'counter': 12.34
Number of cells: 9
wns max 0.00
tns max 0.00
worst slack max 2.5
clk period_min = 7.5 fmax = 133.33
setup violation count 0
hold violation count 0
"""

HOLD_ONLY_FINISH = """\
wns max 0.00
tns max 0.00
worst slack max 2.5
clk period_min = 7.5 fmax = 133.33
setup violation count 0
hold violation count 4
"""


def _fake_orfs(top: str, finish_rpt: str, platform: str = "sky130hd"):
    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", platform, top, "base")
        results = os.path.join(run_dir, "orfs_results", platform, top, "base")
        _write_file(os.path.join(reports, "6_finish.rpt"), finish_rpt)
        _write_file(
            os.path.join(results, "6_final.v"),
            f"module {top}(input clk, output [3:0] q); endmodule",
        )
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    return fake_orfs


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


def test_timing_violation_is_named_but_does_not_fail_the_run(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        monkeypatch.setattr(sm, "_run_orfs", _fake_orfs("counter", VIOLATING_FINISH))
        final = _run_to_completion(workspace, verilog_files=[design], top_module="counter")

        # Locked semantics: the flow produced its artifacts, so the RUN completed.
        assert final["status"] == "completed"
        assert final["auto_checks"]["timing"] == "fail"
        notes = final["check_notes"].lower()
        assert "timing not evaluated" not in notes
        assert "timing not met" in notes
        # The failing MODE is named, not just a verdict.
        assert "setup slack -1137.59 ns" in notes
        assert "12 setup violations" in notes


def test_met_timing_names_the_slack_instead_of_disclaiming(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        monkeypatch.setattr(sm, "_run_orfs", _fake_orfs("counter", MET_FINISH))
        final = _run_to_completion(workspace, verilog_files=[design], top_module="counter")

        assert final["status"] == "completed"
        assert final["auto_checks"]["timing"] == "pass"
        notes = final["check_notes"].lower()
        assert "timing not evaluated" not in notes
        assert "timing met" in notes and "2.50 ns" in notes


def test_hold_violations_alone_fail_the_timing_check():
    """Positive setup slack is not "timing met" when hold paths are violated."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(
            os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "6_finish.rpt"),
            HOLD_ONLY_FINISH,
        )
        meta = {"run_id": "synth_0001", "platform": "sky130hd", "top_module": "counter", "sdc_time_unit": "ns"}
        verdict = sm._timing_guardrail(run_dir, meta)
        assert verdict["status"] == "fail"
        assert "4 hold violations" in verdict["note"]


def test_timing_is_never_blamed_for_a_failed_run(monkeypatch):
    """B2: the "run failed on:" list is derived from an explicit tuple.

    An asdict() sweep would have swept the new timing field into failure
    attribution for a run that failed on equivalence — despite timing being
    deliberately excluded from final_ok.
    """
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        monkeypatch.setattr(sm, "_run_orfs", _fake_orfs("counter", VIOLATING_FINISH))
        monkeypatch.setattr(
            sm, "_run_equiv_check",
            lambda *a, **k: {"status": "fail", "note": "equivalence check failed"},
        )
        final = _run_to_completion(
            workspace, verilog_files=[design], top_module="counter", run_equiv=True
        )

        assert final["status"] == "failed"
        assert final["auto_checks"]["timing"] == "fail"
        failed_on = final["check_notes"].split("run failed on:")[1].split("|")[0]
        assert "equiv" in failed_on
        assert "timing" not in failed_on


def test_partial_flow_has_no_timing_data_and_says_so(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)

        def fake_targets(**kwargs):
            run_dir = kwargs["run_dir"]
            _write_file(
                os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
                "Chip area for module '\\counter': 123.45\n814 7.33E+03 cells\n",
            )
            _write_file(
                os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.v"),
                "module counter(); endmodule",
            )
            _write_file(
                os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "1_synth.odb"),
                "odb",
            )
            return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

        monkeypatch.setattr(sm, "_run_orfs_targets", fake_targets)
        final = _run_to_completion(
            workspace, verilog_files=[design], top_module="counter", max_stage="synth"
        )

        assert final["status"] == "completed"
        assert final["auto_checks"]["timing"] == "skip"
        assert "timing not met" not in final["check_notes"].lower()


def test_adopted_run_carries_the_timing_term_too():
    """B3: _finalize_completed (worker died before finalizing) wrote NO
    auto_checks at all, so a reconciled run had no timing verdict anywhere."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(
            os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "6_finish.rpt"),
            VIOLATING_FINISH,
        )
        _write_file(
            os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "6_final.v"),
            "module counter(); endmodule",
        )
        _write_file(
            os.path.join(run_dir, "run_meta.json"),
            json.dumps(
                {
                    "run_id": "synth_0001",
                    "status": "running",
                    "platform": "sky130hd",
                    "top_module": "counter",
                    "max_stage": "finish",
                    "clock_period_ns": 10.0,
                    "sdc_time_unit": "ns",
                }
            ),
        )

        status = sm.get_synthesis_status("synth_0001", workspace=workspace)
        assert status["status"] == "completed"
        assert status["auto_checks"]["timing"] == "fail"
        assert "timing not met" in (status["check_notes"] or "").lower()

        # Persisted, not just rendered: the run directory is the database.
        with open(os.path.join(run_dir, "run_meta.json"), "r", encoding="utf-8") as f:
            persisted = json.load(f)
        assert persisted["auto_checks"]["timing"] == "fail"


def test_read_side_auto_checks_default_includes_timing():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(
            os.path.join(run_dir, "run_meta.json"),
            json.dumps({"run_id": "synth_0001", "status": "completed", "top_module": "counter"}),
        )
        status = sm.get_synthesis_status("synth_0001", workspace=workspace)
        assert status["auto_checks"]["timing"] == "skip"
