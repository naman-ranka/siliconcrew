"""Wave C (dev#80 error 3, C4-C7): the design report and the diff endpoint.

The report's timing verdict read ORFS's CLAMPED wns, which is 0.00 for every
design that met timing AND for every design whose real slack was never
reported — so the cell said "Met" either way. Its "can run at X MHz" line
divided the clock TARGET, i.e. echoed the input back as an achievement.
"""
import importlib
import json
import os
import tempfile

import pytest

from src.tools import synthesis_manager as sm
from src.tools.design_report import generate_design_report, load_metrics
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


VIOLATING_FINISH = """\
tns max -99.00
wns max 0.00
worst slack max -2.5
clk period_min = 12.5 fmax = 80.0
setup violation count 7
hold violation count 0
Total                  1.00e-03   1.00e-03   1.00e-09   2.00e-03 100.0%
"""

MET_FINISH = """\
tns max 0.00
wns max 0.00
worst slack max 2.5
clk period_min = 7.5 fmax = 133.33
setup violation count 0
hold violation count 0
Total                  1.00e-03   1.00e-03   1.00e-09   2.00e-03 100.0%
"""

SYNTH_STAT = "      100 1.23E+03 cells\nChip area for module '\\demo': 1234.000000\n"


def _seed_run(workspace: str, finish_rpt: str, platform: str = "sky130hd") -> None:
    spec = DesignSpec(
        module_name="demo",
        description="demo",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "demo_spec.yaml"))
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    base = os.path.join(run_dir, "orfs_reports", platform, "demo", "base")
    _write_file(os.path.join(base, "6_finish.rpt"), finish_rpt)
    _write_file(os.path.join(base, "synth_stat.txt"), SYNTH_STAT)
    _write_file(os.path.join(workspace, "synth_runs", "LATEST"), "synth_0001")
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps(
            {
                "run_id": "synth_0001",
                "status": "completed",
                "top_module": "demo",
                "platform": platform,
                "clock_period_ns": 10.0,
                "effective_clock_period_ns": 10.0,
                "sdc_time_unit": "ns",
            }
        ),
    )


def test_report_timing_cell_reads_the_real_slack():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, VIOLATING_FINISH)
        report = generate_design_report(workspace, run_id="synth_0001")
        # Pre-fix: the clamped 0.000 rendered "✅ Met" for a design 2.5 ns short.
        timing_rows = [ln for ln in report.splitlines() if "Slack" in ln or "WNS" in ln]
        assert any("Violated" in ln for ln in timing_rows), timing_rows
        assert not any("Met" in ln for ln in timing_rows), timing_rows
        assert "-2.500" in report
        # Achieved period = target - slack in BOTH branches: 10 - (-2.5).
        assert "80.0 MHz" in report


def test_report_met_path_states_the_achieved_frequency_not_the_target():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, MET_FINISH, platform="asap7")
        report = generate_design_report(workspace, run_id="synth_0001")
        assert "MET" in report
        # The lie: 1000/target_period = 100.0 MHz, printed as an achievement.
        assert "100.0 MHz" not in report
        assert "133.3 MHz" in report
        # asap7's default ORFS corner is best-case: an unlabelled figure would
        # be its own overstatement.
        assert "BC/FF (best-case)" in report


def test_load_metrics_carries_the_new_timing_fields():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, MET_FINISH)
        metrics = load_metrics(workspace, run_id="synth_0001")
        assert metrics["worst_slack_ns"] == pytest.approx(2.5)
        assert metrics["fmax_mhz"] == pytest.approx(133.33)
        assert metrics["timing_corner"] == "TT (typical)"


def test_the_dead_ppa_parsers_are_gone():
    """C4/C5: two more WNS parsers with crude regexes — one reachable only as
    design_report's tier-3 fallback and untested, one with zero call sites."""
    with pytest.raises(ImportError):
        importlib.import_module("src.tools.get_ppa")
    assert not hasattr(sm, "_extract_summary_metrics")
