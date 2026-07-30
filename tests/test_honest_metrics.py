"""Wave C (dev#70): honest synthesis metrics.

ORFS's ``report_wns`` clamps positive slack to 0 BY DESIGN (OpenSTA
``search/Search.tcl``), so ``wns_ns`` keeps its tool-faithful meaning and the
REAL margin comes from the ``worst slack max`` line that sits right next to it
in 6_finish.rpt. Deriving Fmax from the clamped value made every timing-met run
echo its own clock target back as an "achieved" frequency (staging run
synth_0003: 100.0 MHz reported for a design that closes at 8.1 GHz).
"""
import json
import os
import tempfile

import pytest

from src.tools import synthesis_manager as sm


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# Modeled on the REAL asap7 6_finish.rpt from staging run synth_0003 (times in
# ps, power in Watts): the clamped wns and the real worst slack side by side.
ASAP7_FINISH_MET = """\
==========================================================================
finish report_tns
--------------------------------------------------------------------------
tns max 0.00

==========================================================================
finish report_wns
--------------------------------------------------------------------------
wns max 0.00

==========================================================================
finish report_worst_slack
--------------------------------------------------------------------------
worst slack max 9876.69

==========================================================================
finish report_clock_min_period
--------------------------------------------------------------------------
clk period_min = 123.31 fmax = 8109.80

==========================================================================
finish report_check_types
--------------------------------------------------------------------------
setup violation count 0
hold violation count 0
max slew violation count 0
max cap violation count 0
max fanout violation count 0

==========================================================================
finish report_power
--------------------------------------------------------------------------
Total                  2.78e-03   7.27e-04   1.53e-06   3.51e-03 100.0%
"""

# A design that closes nothing (sky130hd, ns units).
SKY130_FINISH_VIOLATING = """\
tns max -9999.00
wns max -1137.59
worst slack max -1137.59
clk period_min = 1147.59 fmax = 0.87
setup violation count 12
hold violation count 0
max slew violation count 0
max cap violation count 0
max fanout violation count 0
Total                  1.23e-04   2.34e-05   1.11e-06   4.27e-02 100.0%
"""

# No constrained timing paths at all: OpenSTA prints INF (OpenROAD #4425).
SKY130_FINISH_UNCONSTRAINED = """\
tns max 0.00
wns max 0.00
worst slack max INF
clk period_min = 0.00 fmax = INF
setup violation count 0
hold violation count 0
"""

# The pre-Wave-C shape: clamped wns only, no worst-slack / min-period lines.
SKY130_FINISH_NO_SLACK_LINES = """\
tns max 0.00
wns max 0.00
setup violation count 0
hold violation count 0
Total                  1.23e-04   2.34e-05   1.11e-06   4.27e-02 100.0%
"""

SYNTH_STAT = """\
   Chip area for module '\\alu4': 1344.407220

   814  7.33E+03 cells
"""


def _make_run(workspace: str, finish_rpt: str, meta: dict, run_id: str = "synth_0001") -> str:
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    platform = meta.get("platform", "sky130hd")
    top = meta.get("top_module", "alu4")
    base = os.path.join(run_dir, "orfs_reports", platform, top, "base")
    _write_file(os.path.join(base, "6_finish.rpt"), finish_rpt)
    _write_file(os.path.join(base, "synth_stat.txt"), SYNTH_STAT)
    _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(dict(meta, run_id=run_id)))
    return run_dir


ASAP7_META = {
    "status": "completed",
    "platform": "asap7",
    "top_module": "alu4",
    "max_stage": "finish",
    "requested_clock_period_ns": 10.0,
    "effective_clock_period_ns": 10.0,
    "clock_period_ns": 10.0,
    "sdc_time_unit": "ps",
}

SKY130_META = {
    "status": "completed",
    "platform": "sky130hd",
    "top_module": "alu4",
    "max_stage": "finish",
    "requested_clock_period_ns": 10.0,
    "effective_clock_period_ns": 10.0,
    "clock_period_ns": 10.0,
    "sdc_time_unit": "ns",
}


def test_real_asap7_report_reports_real_slack_and_fmax():
    """The staging reproduction: 100.0 MHz (the target) -> 8109.8 MHz (achieved)."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _make_run(workspace, ASAP7_FINISH_MET, ASAP7_META)

        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        m = result["metrics"]
        # wns_ns keeps ORFS's clamped semantics (unchanged, deliberately).
        assert m["wns_ns"] == pytest.approx(0.0)
        # ...and the REAL margin is now surfaced, ps -> ns.
        assert m["worst_slack_ns"] == pytest.approx(9.87669)
        assert m["clock_period_min_ns"] == pytest.approx(0.12331)
        # ORFS emits fmax in MHz on every platform: used verbatim, never rescaled.
        assert m["fmax_mhz"] == pytest.approx(8109.80)
        assert m["timing_met"] is True
        assert m["timing_corner"] == "BC/FF (best-case)"

        # The shared finalizer agrees with the read path, field for field.
        summary = sm._compute_summary_metrics(run_dir, dict(ASAP7_META, run_id="synth_0001"))
        assert summary["worst_slack_ns"] == pytest.approx(9.87669)
        assert summary["fmax_mhz"] == pytest.approx(8109.80)
        assert summary["timing_met"] is True


def test_derived_fmax_cross_checks_against_the_reports_own_fmax():
    """1000/(target - worst slack) approximates ORFS's own fmax within 0.01%.

    The derivation is the LABELLED fallback (OpenSTA's find_clk_min_period
    iterates properly); this pins that it is at least arithmetically sane.
    """
    derived = 1000.0 / (10.0 - 9.87669)
    assert derived == pytest.approx(8109.64, abs=0.5)
    with tempfile.TemporaryDirectory() as workspace:
        _make_run(workspace, ASAP7_FINISH_MET, ASAP7_META)
        parsed = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")["metrics"]
        assert parsed["fmax_mhz"] == pytest.approx(derived, rel=0.001)


def test_violating_report_is_not_met():
    with tempfile.TemporaryDirectory() as workspace:
        _make_run(workspace, SKY130_FINISH_VIOLATING, SKY130_META)
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        m = result["metrics"]
        assert m["worst_slack_ns"] == pytest.approx(-1137.59)
        assert m["timing_met"] is False
        assert m["timing_corner"] == "TT (typical)"
        assert result["violations"]["setup"] == 12


def test_unconstrained_design_is_distinct_from_unknown():
    """``INF`` means "no constrained timing paths", not "unknown"."""
    with tempfile.TemporaryDirectory() as workspace:
        _make_run(workspace, SKY130_FINISH_UNCONSTRAINED, SKY130_META)
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        m = result["metrics"]
        assert m["worst_slack_ns"] is None
        assert m["fmax_mhz"] is None
        assert m["timing_met"] is None
        assert any("no constrained timing paths" in n for n in result["parse_notes"])
        # period_min = 0.00 must never reach a division.
        assert m["clock_period_min_ns"] == pytest.approx(0.0)


def test_missing_slack_lines_yield_no_fmax_not_the_target_echo():
    with tempfile.TemporaryDirectory() as workspace:
        _make_run(workspace, SKY130_FINISH_NO_SLACK_LINES, SKY130_META)
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        m = result["metrics"]
        assert m["worst_slack_ns"] is None
        assert m["timing_met"] is None
        # The bug: 1000/(10.0 - 0.0) = 100.0 MHz, i.e. the clock target echoed
        # back as an achieved frequency.
        assert m["fmax_mhz"] != pytest.approx(100.0)
        assert m["fmax_mhz"] is None
        assert any("fmax" in n.lower() for n in result["parse_notes"])


def test_negative_clamped_wns_is_real_slack_and_still_derives_fmax():
    """report_wns clamps POSITIVE slack only: a negative wns IS the worst slack.

    So a legacy report without the worst-slack line still derives an honest
    (labelled) fmax when timing missed.
    """
    with tempfile.TemporaryDirectory() as workspace:
        _make_run(
            workspace,
            "tns max -9999.00\nwns max -2.0\nsetup violation count 3\n",
            SKY130_META,
        )
        m = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")["metrics"]
        assert m["fmax_mhz"] == pytest.approx(1000.0 / 12.0, abs=0.01)
        assert m["timing_met"] is False


def test_summary_metrics_carry_the_disclosure_and_a_schema_stamp():
    """C3/B1: the persisted snapshot must not read as more certain than the read path."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _make_run(workspace, SKY130_FINISH_NO_SLACK_LINES, SKY130_META)
        summary = sm._compute_summary_metrics(run_dir, dict(SKY130_META, run_id="synth_0001"))
        assert summary["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION
        assert summary["fmax_mhz"] is None
        assert summary["timing_note"] and "fmax" in summary["timing_note"].lower()


def _seed_index(workspace: str, run_id: str) -> None:
    _write_file(
        os.path.join(workspace, "synth_runs", "index.json"),
        json.dumps({"runs": [{"run_id": run_id, "status": "completed", "updated_at": "2026-07-30T00:00:00+00:00"}], "jobs": []}),
    )


def test_runs_list_self_heals_stale_metrics_then_stops_rewriting():
    """B1: the persisted snapshot is what the runs list/PPA hero read.

    Pre-fix the self-heal fired only on a None cell_count/fmax, so a completed
    run kept its target-echo fmax forever (detail panel 8109.8 vs card 100.0),
    while partial runs with a permanently-None fmax were rewritten on EVERY
    list read.
    """
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _make_run(workspace, ASAP7_FINISH_MET, ASAP7_META)
        _seed_index(workspace, "synth_0001")
        meta_path = os.path.join(run_dir, "run_meta.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # A snapshot written by the pre-Wave-C finalizer: the echo, no stamp.
        meta["summary_metrics"] = {
            "area_um2": 1344.40722,
            "cell_count": 814,
            "wns_ns": 0.0,
            "tns_ns": 0.0,
            "power_uw": 3510.0,
            "power_mw": 3.51,
            "fmax_mhz": 100.0,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)

        items = sm.list_synthesis_runs(workspace)
        healed = items[0]["summary_metrics"]
        assert healed["fmax_mhz"] == pytest.approx(8109.80)
        assert healed["worst_slack_ns"] == pytest.approx(9.87669)
        assert healed["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION

        # ...and a second read must NOT rewrite run_meta again (write amplification).
        mtime = os.path.getmtime(meta_path)
        sm.list_synthesis_runs(workspace)
        assert os.path.getmtime(meta_path) == mtime


def test_partial_run_with_no_reports_is_stamped_once_not_rewritten_forever():
    """The write-amplification half of B1: a synth-only run's fmax is legitimately
    None forever, so the old ``fmax_mhz is None`` condition fired on every read."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(
            os.path.join(run_dir, "orfs_reports", "sky130hd", "alu4", "base", "synth_stat.txt"),
            SYNTH_STAT,
        )
        meta = dict(SKY130_META, run_id="synth_0001", max_stage="synth")
        meta["summary_metrics"] = {
            "area_um2": 1344.40722,
            "cell_count": 814,
            "wns_ns": None,
            "tns_ns": None,
            "power_uw": None,
            "power_mw": None,
            "fmax_mhz": None,
        }
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
        _seed_index(workspace, "synth_0001")

        sm.list_synthesis_runs(workspace)
        meta_path = os.path.join(run_dir, "run_meta.json")
        mtime = os.path.getmtime(meta_path)
        sm.list_synthesis_runs(workspace)
        assert os.path.getmtime(meta_path) == mtime
