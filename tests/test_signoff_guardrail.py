"""
Tests for summary_metrics WNS/TNS visibility after synthesis completes.

The core requirement: when ORFS completes (docker exit 0) and 6_finish.rpt
is written, the agent must always receive the correct wns_ns and tns_ns values
in summary_metrics — including negative values for timing violations.

The tool should NOT interpret timing pass/fail. It surfaces raw numbers so
the agent can reason about them. signoff: pass means ORFS completed and
produced artifacts, not that timing closed.
"""
import json
import os
import tempfile
import time

import pytest

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file
from src.tools.synthesis_manager import (
    _parse_finish_report,
    _find_report_file,
    get_synthesis_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_dir(tmp_path, platform="sky130hd", top="dut"):
    report_dir = tmp_path / "orfs_reports" / platform / top / "base"
    report_dir.mkdir(parents=True)
    result_dir = tmp_path / "orfs_results" / platform / top / "base"
    result_dir.mkdir(parents=True)
    (result_dir / "6_final.v").write_text("module dut(); endmodule\n")
    runs_dir = tmp_path / "synth_runs" / "synth_0001"
    runs_dir.mkdir(parents=True)
    return str(tmp_path), str(report_dir), str(runs_dir)


def _write_finish_rpt(report_dir: str, wns: float, tns: float = 0.0, power_w: float = 1.5e-4):
    content = (
        f"wns max {wns:.3f}\n"
        f"tns max {tns:.3f}\n"
        "setup violation count 0\n"
        "hold violation count 0\n"
        f"Total  1.23e-04  2.34e-05  1.11e-06  {power_w:.3e}  100.0%\n"
    )
    path = os.path.join(report_dir, "6_finish.rpt")
    with open(path, "w") as f:
        f.write(content)
    return path


def _write_synth_stat(run_dir: str, area: float = 116.362, cells: int = 42):
    stat_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "dut", "base")
    os.makedirs(stat_dir, exist_ok=True)
    content = f"Chip area for module '\\dut': {area}\nNumber of cells: {cells}\n"
    path = os.path.join(stat_dir, "synth_stat.txt")
    with open(path, "w") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# _parse_finish_report — verify it handles the ORFS "wns max <value>" format
# ---------------------------------------------------------------------------

def test_parse_finish_report_negative_wns(tmp_path):
    """The critical case: wns max -2.19 must parse to -2.19, not null."""
    rpt = tmp_path / "6_finish.rpt"
    rpt.write_text(
        "wns max -2.19\n"
        "tns max -64.45\n"
        "setup violation count 12\n"
        "hold violation count 0\n"
        "Total  1.39e-01  2.00e-02  1.00e-04  1.39e-01  100.0%\n"
    )
    data = _parse_finish_report(str(rpt))
    assert data["wns_ns"] == pytest.approx(-2.19)
    assert data["tns_ns"] == pytest.approx(-64.45)


def test_parse_finish_report_positive_wns(tmp_path):
    rpt = tmp_path / "6_finish.rpt"
    rpt.write_text(
        "wns max 0.31\n"
        "tns max 0.00\n"
        "setup violation count 0\n"
        "hold violation count 0\n"
        "Total  3.00e-04  5.00e-05  1.00e-06  3.00e-04  100.0%\n"
    )
    data = _parse_finish_report(str(rpt))
    assert data["wns_ns"] == pytest.approx(0.31)
    assert data["tns_ns"] == pytest.approx(0.0)


def test_parse_finish_report_zero_wns(tmp_path):
    """WNS = 0.00 (edge-met timing) must parse as 0.0, not null."""
    rpt = tmp_path / "6_finish.rpt"
    rpt.write_text("wns max 0.00\ntns max 0.00\n")
    data = _parse_finish_report(str(rpt))
    assert data["wns_ns"] == pytest.approx(0.0)


def test_parse_finish_report_power(tmp_path):
    rpt = tmp_path / "6_finish.rpt"
    rpt.write_text(
        "wns max 0.10\ntns max 0.00\n"
        "Total  1.23e-04  2.34e-05  1.11e-06  1.50e-04  100.0%\n"
    )
    data = _parse_finish_report(str(rpt))
    assert data["power_uw"] == pytest.approx(150.0, rel=1e-3)


# ---------------------------------------------------------------------------
# _find_report_file — confirm it finds 6_finish.rpt in nested ORFS structure
# ---------------------------------------------------------------------------

def test_find_report_file_finds_finish_rpt(tmp_path):
    nested = tmp_path / "orfs_reports" / "sky130hd" / "fir_filter" / "base"
    nested.mkdir(parents=True)
    (nested / "6_finish.rpt").write_text("wns max -2.19\n")

    result = _find_report_file(str(tmp_path), "6_finish.rpt")
    assert result is not None
    assert result.endswith("6_finish.rpt")


def test_find_report_file_returns_none_when_absent(tmp_path):
    (tmp_path / "orfs_reports").mkdir()
    result = _find_report_file(str(tmp_path), "6_finish.rpt")
    assert result is None


# ---------------------------------------------------------------------------
# get_synthesis_metrics — the public tool the agent calls
# Verify it returns wns_ns correctly (not null) from a completed run_dir
# ---------------------------------------------------------------------------

def _make_complete_run(tmp_path, wns: float, tns: float = 0.0):
    """Build a minimal completed synth run on disk that get_synthesis_metrics can read."""
    run_id = "synth_0001"
    runs_root = tmp_path / "synth_runs"
    run_dir = runs_root / run_id
    report_dir = run_dir / "orfs_reports" / "sky130hd" / "dut" / "base"
    report_dir.mkdir(parents=True)

    # LATEST pointer
    (runs_root / "LATEST").write_text(run_id)

    # run_meta.json
    with open(run_dir / "run_meta.json", "w") as f:
        json.dump({"run_id": run_id, "top_module": "dut", "platform": "sky130hd"}, f)

    # 6_finish.rpt with realistic content
    (report_dir / "6_finish.rpt").write_text(
        f"wns max {wns:.3f}\n"
        f"tns max {tns:.3f}\n"
        "setup violation count 0\n"
        "hold violation count 0\n"
        "Total  1.23e-04  2.34e-05  1.11e-06  1.50e-04  100.0%\n"
    )

    # synth_stat.txt for area
    (report_dir / "synth_stat.txt").write_text(
        "Chip area for module '\\dut': 116.362\nNumber of cells: 42\n"
    )

    return str(tmp_path)


def test_get_synthesis_metrics_returns_negative_wns(tmp_path):
    """
    Core regression: get_synthesis_metrics must return wns_ns=-2.19 when
    6_finish.rpt contains 'wns max -2.19'. Previously this returned null
    because _extract_summary_metrics regex missed the 'max' keyword.
    """
    workspace = _make_complete_run(tmp_path, wns=-2.19, tns=-64.45)
    result = get_synthesis_metrics(workspace)

    assert result["status"] == "ok"
    assert result["metrics"]["wns_ns"] == pytest.approx(-2.19)
    assert result["metrics"]["tns_ns"] == pytest.approx(-64.45)


def test_get_synthesis_metrics_returns_positive_wns(tmp_path):
    workspace = _make_complete_run(tmp_path, wns=0.31, tns=0.0)
    result = get_synthesis_metrics(workspace)

    assert result["status"] == "ok"
    assert result["metrics"]["wns_ns"] == pytest.approx(0.31)


def test_get_synthesis_metrics_returns_zero_wns(tmp_path):
    """Edge-met timing (WNS=0.00) must not be returned as null."""
    workspace = _make_complete_run(tmp_path, wns=0.0, tns=0.0)
    result = get_synthesis_metrics(workspace)

    assert result["status"] == "ok"
    assert result["metrics"]["wns_ns"] == pytest.approx(0.0)


def test_get_synthesis_metrics_returns_area(tmp_path):
    workspace = _make_complete_run(tmp_path, wns=0.10)
    result = get_synthesis_metrics(workspace)

    assert result["metrics"]["area_um2"] == pytest.approx(116.362)


# ---------------------------------------------------------------------------
# signoff semantics: tool reports completion, agent interprets timing
# ---------------------------------------------------------------------------

def test_signoff_does_not_encode_timing_verdict(tmp_path):
    """
    signoff: pass means ORFS completed and produced artifacts.
    It must NOT mean 'timing closed'. A negative WNS run can have signoff:pass —
    the agent is responsible for reading wns_ns and deciding.
    """
    workspace = _make_complete_run(tmp_path, wns=-2.19)
    result = get_synthesis_metrics(workspace)

    # The tool surfaces the raw negative WNS — agent can see it
    assert result["metrics"]["wns_ns"] < 0
    # But the tool itself does not say "failed" because of this
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Issue #64: the timing verdict is its OWN axis
#
# signoff stays artifact/log-only (see the test above — that separation is
# deliberate and load-bearing). What was dishonest was the SUMMARY: a run that
# reached GDS with WNS = -1137 ns reported check_notes "All guardrails passed".
# auto_checks.timing + the composed note fix the summary without touching the
# run status (the flow really did complete) or repurposing signoff.
# ---------------------------------------------------------------------------

def _timing_workspace(workspace: str, platform: str = "sky130hd") -> str:
    """Real dispatch path (spec + design on disk), ORFS stubbed."""
    design = os.path.join(workspace, "counter.v")
    os.makedirs(os.path.dirname(design), exist_ok=True)
    with open(design, "w", encoding="utf-8") as f:
        f.write(
            "module counter(input clk, input rst, output reg [3:0] q); "
            "always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule"
        )
    spec = DesignSpec(
        module_name="counter",
        description="counter",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))
    return design


def _fake_full_flow_orfs(platform: str, wns: float, tns: float, success: bool = True):
    """Stub for _run_orfs producing a complete finish-stage artifact set.

    ``wns``/``tns`` are written in the PLATFORM's report unit (ps on asap7),
    exactly like real ORFS reports.
    """

    def fake(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", platform, "counter", "base")
        results = os.path.join(run_dir, "orfs_results", platform, "counter", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write(
                f"wns max {wns}\n"
                f"tns max {tns}\n"
                "setup violation count 0\n"
                "hold violation count 0\n"
                "Total  1.23e-04  2.34e-05  1.11e-06  1.50e-04  100.0%\n"
            )
        with open(os.path.join(reports, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write("Chip area for module '\\counter': 116.362\n42 116.362 cells\n")
        with open(os.path.join(results, "6_final.v"), "w", encoding="utf-8") as f:
            f.write("module counter(input clk, input rst, output [3:0] q); endmodule")
        with open(os.path.join(results, "6_final.gds"), "w", encoding="utf-8") as f:
            f.write("gds")
        return {"success": success, "stdout": "ok", "stderr": "", "command": "fake"}

    return fake


def _poll_final(run_id: str, workspace: str):
    for _ in range(80):
        status = sm.get_synthesis_status(run_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("run did not reach a terminal status")


# ---- _timing_verdict unit tests ------------------------------------------------


def test_timing_verdict_fail_on_negative_wns():
    verdict, note = sm._timing_verdict({"wns_ns": -1137.59, "tns_ns": -50123.0})
    assert verdict == "fail"
    assert "TIMING NOT MET" in note
    assert "-1137.59" in note


def test_timing_verdict_pass_on_nonnegative_wns():
    assert sm._timing_verdict({"wns_ns": 0.31, "tns_ns": 0.0})[0] == "pass"
    # Edge-met timing (WNS exactly 0) is met, not violated.
    assert sm._timing_verdict({"wns_ns": 0.0, "tns_ns": 0.0})[0] == "pass"


def test_timing_verdict_skips_without_wns():
    verdict, note = sm._timing_verdict({"wns_ns": None, "tns_ns": None})
    assert verdict == "skip"
    assert "not evaluated" in note
    # No metrics at all (partial flow) behaves the same.
    assert sm._timing_verdict(None)[0] == "skip"
    assert sm._timing_verdict({})[0] == "skip"


# ---- end-to-end through the real worker ----------------------------------------


def test_violated_timing_is_reported_and_run_stays_completed(tmp_path, monkeypatch):
    """The #64 repro: catastrophic negative slack, artifacts all clean."""
    workspace = str(tmp_path / "ws")
    os.makedirs(workspace, exist_ok=True)
    design = _timing_workspace(workspace)
    monkeypatch.setattr(sm, "_run_orfs", _fake_full_flow_orfs("sky130hd", wns=-1137.59, tns=-50123.0))

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="counter", platform="sky130hd"
    )
    final = _poll_final(started["run_id"], workspace)

    # The flow completed and the artifacts are clean — that stays true.
    assert final["status"] == "completed"
    assert final["auto_checks"]["signoff"] == "pass"
    # ...but the summary no longer claims timing passed.
    assert final["auto_checks"]["timing"] == "fail"
    assert "TIMING NOT MET" in final["check_notes"]
    assert "All guardrails passed" not in final["check_notes"]
    assert final["summary_metrics"]["wns_ns"] == pytest.approx(-1137.59)


def test_met_timing_reports_pass(tmp_path, monkeypatch):
    workspace = str(tmp_path / "ws")
    os.makedirs(workspace, exist_ok=True)
    design = _timing_workspace(workspace)
    monkeypatch.setattr(sm, "_run_orfs", _fake_full_flow_orfs("sky130hd", wns=0.31, tns=0.0))

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="counter", platform="sky130hd"
    )
    final = _poll_final(started["run_id"], workspace)

    assert final["status"] == "completed"
    assert final["auto_checks"]["timing"] == "pass"
    assert "timing met" in final["check_notes"]
    assert "TIMING NOT MET" not in final["check_notes"]


def test_partial_flow_makes_no_timing_claim(tmp_path, monkeypatch):
    """max_stage='synth' never produces 6_finish.rpt — timing is honestly
    'skip', and the note must not claim timing either way."""
    workspace = str(tmp_path / "ws")
    os.makedirs(workspace, exist_ok=True)
    design = _timing_workspace(workspace)

    def fake_targets(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write("Chip area for module '\\counter': 116.362\n42 116.362 cells\n")
        with open(os.path.join(results, "1_synth.v"), "w", encoding="utf-8") as f:
            f.write("module counter(); endmodule")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs_targets", fake_targets)

    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter",
        platform="sky130hd",
        max_stage="synth",
    )
    final = _poll_final(started["run_id"], workspace)

    assert final["status"] == "completed"
    assert final["auto_checks"]["timing"] == "skip"
    assert "TIMING NOT MET" not in final["check_notes"]
    assert "timing met" not in final["check_notes"]


def test_asap7_timing_note_is_in_canonical_ns(tmp_path, monkeypatch):
    """Ties #63 to #64: asap7 reports are in ps. The note must print the
    canonical ns value (-1.13759 ns), never the raw -1137.59."""
    workspace = str(tmp_path / "ws")
    os.makedirs(workspace, exist_ok=True)
    design = _timing_workspace(workspace)
    monkeypatch.setattr(sm, "_run_orfs", _fake_full_flow_orfs("asap7", wns=-1137.59, tns=-50123.0))

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="counter", platform="asap7"
    )
    final = _poll_final(started["run_id"], workspace)

    run_meta_path = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(run_meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["sdc_time_unit"] == "ps"

    assert final["auto_checks"]["timing"] == "fail"
    assert "-1.13759 ns" in final["check_notes"]
    assert "-1137.59" not in final["check_notes"]


def test_asap7_signoff_recovery_note_is_in_canonical_ns(tmp_path, monkeypatch):
    """The recovery path's note interpolates report times too (#63/#64): raw ps
    values must not be printed unlabeled as if they were ns."""
    workspace = str(tmp_path / "ws")
    os.makedirs(workspace, exist_ok=True)
    design = _timing_workspace(workspace)
    monkeypatch.setattr(
        sm, "_run_orfs", _fake_full_flow_orfs("asap7", wns=-1137.59, tns=-50123.0, success=False)
    )

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="counter", platform="asap7"
    )
    final = _poll_final(started["run_id"], workspace)

    # ORFS returned nonzero AND timing is dirty -> signoff fails, run fails.
    assert final["status"] == "failed"
    assert final["auto_checks"]["signoff"] == "fail"
    assert "final timing is not clean: WNS=-1.13759 ns" in final["check_notes"]
