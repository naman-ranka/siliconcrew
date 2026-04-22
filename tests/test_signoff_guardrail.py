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

import pytest

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
