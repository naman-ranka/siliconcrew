"""Wave C adversarial review: the consumer surfaces the metrics fix didn't reach.

B-1 is the blocking one: the design report kept its own copy of the target echo
in an arithmetic fallback, so a run that get_synthesis_metrics honestly reports
as "no slack data" still rendered "✅ Met ... 100.0 MHz".
"""
import json
import os
import tempfile

import pytest

from src.tools.design_report import generate_design_report, load_metrics
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file
from src.utils.attempt_logger import _extract_synth_metrics

PLATFORM = "sky130hd"
TOP = "demo"

# The pre-Wave-C report shape: ORFS's clamped wns and nothing else. The clamp
# makes 0.00 mean "positive slack, magnitude not reported" — not "zero margin".
CLAMPED_ONLY_FINISH = """\
tns max 0.00
wns max 0.00
setup violation count 0
hold violation count 0
Total                  1.00e-03   1.00e-03   1.00e-09   2.00e-03 100.0%
"""

UNCONSTRAINED_FINISH = """\
tns max 0.00
wns max 0.00
worst slack max INF
clk period_min = 0.00 fmax = INF
setup violation count 0
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


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _seed_run(workspace: str, finish_rpt: str, platform: str = PLATFORM) -> None:
    spec = DesignSpec(
        module_name=TOP, description="demo", clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, f"{TOP}_spec.yaml"))
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    base = os.path.join(run_dir, "orfs_reports", platform, TOP, "base")
    _write_file(os.path.join(base, "6_finish.rpt"), finish_rpt)
    _write_file(os.path.join(base, "synth_stat.txt"), SYNTH_STAT)
    _write_file(os.path.join(workspace, "synth_runs", "LATEST"), "synth_0001")
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({"run_id": "synth_0001", "status": "completed", "top_module": TOP,
                    "platform": platform, "clock_period_ns": 10.0,
                    "effective_clock_period_ns": 10.0, "sdc_time_unit": "ns"}),
    )


# --- B-1: the report's own copy of the target echo ---------------------------

def test_clamped_only_report_states_no_verdict_and_no_frequency():
    """1000/(target - 0.0) IS the target. The report must not print a timing
    verdict or a frequency it cannot justify — get_synthesis_metrics already
    returns fmax null for this exact run."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, CLAMPED_ONLY_FINISH)
        report = generate_design_report(workspace, run_id="synth_0001")

        assert "100.0 MHz" not in report
        assert "Timing requirement MET" not in report
        assert "Timing requirement NOT MET" not in report
        # The clamped number is still shown — labelled for what it is.
        assert "ORFS-clamped" in report
        # ...and the reason there is no verdict is stated, not left blank.
        assert "clamp" in report.lower()


def test_unconstrained_report_says_so_instead_of_claiming_met():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, UNCONSTRAINED_FINISH)
        report = generate_design_report(workspace, run_id="synth_0001")
        assert "100.0 MHz" not in report
        assert "Timing requirement MET" not in report
        assert "no constrained timing paths" in report.lower()


def test_met_report_is_unchanged_by_the_gate():
    """The B-1 fix must not mute a run that DOES have real slack."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, MET_FINISH)
        report = generate_design_report(workspace, run_id="synth_0001")
        assert "Timing requirement MET" in report
        assert "133.3 MHz" in report


def test_load_metrics_carries_the_disclosure():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_run(workspace, UNCONSTRAINED_FINISH)
        metrics = load_metrics(workspace, run_id="synth_0001")
        assert "no constrained timing paths" in (metrics.get("timing_note") or "")


# --- S-5: the same nesting bug as C6, in the attempt summary -----------------

def test_attempt_logger_reads_nested_ppa():
    """get_synthesis_metrics' JSON nests PPA under "metrics"; reading the
    wrapper's top level logged None for every attempt."""
    payload = json.dumps({
        "status": "ok",
        "run_id": "synth_0001",
        "metrics": {"wns_ns": -0.25, "tns_ns": -1.5, "worst_slack_ns": -0.25},
    })
    wns, tns = _extract_synth_metrics(payload)
    assert wns == pytest.approx(-0.25)
    assert tns == pytest.approx(-1.5)


def test_attempt_logger_still_reads_a_flat_payload():
    """Older logged results (and save_metrics output) are flat — keep reading them."""
    wns, tns = _extract_synth_metrics(json.dumps({"wns_ns": 0.5, "tns_ns": 0.0}))
    assert wns == pytest.approx(0.5)
    assert tns == pytest.approx(0.0)
