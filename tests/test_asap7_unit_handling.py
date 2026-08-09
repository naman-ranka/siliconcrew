"""Issue #63: per-platform SDC/report time units, canonical-ns API.

asap7's liberty time unit is ps: the SDC period must be converted from the
canonical clock_period_ns at generation, and STA report times normalized back
to ns at parse — gated on the persisted ``sdc_time_unit`` marker so runs
finalized under the old behavior are never silently reinterpreted.
"""
import json
import os
import tempfile
import time

import pytest

from src.tools import synthesis_manager as sm
from src.tools.pdk_units import ns_to_platform_time, platform_time_unit, time_unit_to_ns
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _poll_final(run_id: str, workspace: str):
    for _ in range(80):
        status = sm.get_synthesis_status(run_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    return None


def _dispatch_constraints_only(workspace: str, platform: str, clock_period_ns: float):
    """Constraints-only dry run: exercises the real dispatch path (SDC write +
    run_meta persistence) without executing ORFS."""
    design = os.path.join(workspace, "counter.v")
    _write_file(
        design,
        "module counter(input clk, input rst, output reg [3:0] q); "
        "always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule",
    )
    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter",
        platform=platform,
        clock_period_ns=clock_period_ns,
        max_stage="constraints",
    )
    final = _poll_final(started["run_id"], workspace)
    assert final is not None and final["status"] == "completed"
    run_dir = os.path.join(workspace, "synth_runs", started["run_id"])
    with open(os.path.join(run_dir, "constraints.sdc"), "r", encoding="utf-8") as f:
        sdc = f.read()
    with open(os.path.join(run_dir, "run_meta.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)
    return sdc, meta


# Fragments modeled on a real asap7 6_finish.rpt (times in ps, power in Watts)
# with representative negative slack.
ASAP7_FINISH_RPT = """\
==========================================================================
finish report_tns
--------------------------------------------------------------------------
tns max -2276.18

==========================================================================
finish report_wns
--------------------------------------------------------------------------
wns max -27.40

==========================================================================
finish report_power
--------------------------------------------------------------------------
Group                  Internal  Switching    Leakage      Total
                          Power      Power      Power      Power (Watts)
----------------------------------------------------------------
Sequential             1.66e-03   5.87e-06   1.76e-07   1.67e-03  47.4%
Combinational          5.01e-05   3.70e-05   1.31e-06   8.84e-05   2.5%
Clock                  1.07e-03   6.84e-04   4.62e-08   1.76e-03  50.0%
Macro                  0.00e+00   0.00e+00   0.00e+00   0.00e+00   0.0%
Total                  2.78e-03   7.27e-04   1.53e-06   3.51e-03 100.0%
"""

ASAP7_SYNTH_STAT = """\
   Chip area for module '\\GCN_core': 1344.407220

   814  7.33E+03 cells
"""

ASAP7_CTS_RPT = """\
==========================================================================
cts final report_wns
--------------------------------------------------------------------------
wns max 0.00

==========================================================================
cts final report_worst_slack
--------------------------------------------------------------------------
worst slack max 26.55

==========================================================================
cts final report_clock_min_period
--------------------------------------------------------------------------
clk period_min = 1173.45 fmax = 852.19
"""


def _make_asap7_run(workspace: str, run_meta: dict) -> str:
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    base = os.path.join(run_dir, "orfs_reports", "asap7", "GCN_core", "base")
    _write_file(os.path.join(base, "6_finish.rpt"), ASAP7_FINISH_RPT)
    _write_file(os.path.join(base, "synth_stat.txt"), ASAP7_SYNTH_STAT)
    _write_file(os.path.join(base, "4_cts_final.rpt"), ASAP7_CTS_RPT)
    _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(run_meta))
    return run_dir


NEW_ASAP7_META = {
    "run_id": "synth_0001",
    "status": "completed",
    "platform": "asap7",
    "top_module": "GCN_core",
    "max_stage": "finish",
    "requested_clock_period_ns": 1.2,
    "effective_clock_period_ns": 1.2,
    "clock_period_ns": 1.2,
    "sdc_time_unit": "ps",
}


def test_pdk_units_table():
    assert platform_time_unit("asap7") == "ps"
    assert platform_time_unit("sky130hd") == "ns"
    assert platform_time_unit("some-unknown-platform") == "ns"
    assert platform_time_unit(None) == "ns"
    assert ns_to_platform_time(10.0, "asap7") == 10000.0
    assert ns_to_platform_time(10.0, "sky130hd") == 10.0
    assert time_unit_to_ns(-1137.59, "ps") == pytest.approx(-1.13759)
    assert time_unit_to_ns(0.34, "ns") == pytest.approx(0.34)
    assert time_unit_to_ns(None, "ps") is None


def test_asap7_dispatch_writes_converted_sdc_and_marker():
    with tempfile.TemporaryDirectory() as workspace:
        sdc, meta = _dispatch_constraints_only(workspace, platform="asap7", clock_period_ns=10.0)
        assert "create_clock -period 10000.0" in sdc
        assert "-period 10 " not in sdc  # the raw ns value must NOT reach the ps SDC
        assert meta["sdc_time_unit"] == "ps"
        # The API/run_meta contract stays canonical ns on every platform.
        assert meta["requested_clock_period_ns"] == 10.0
        assert meta["effective_clock_period_ns"] == 10.0
        assert meta["clock_period_ns"] == 10.0


def test_sky130hd_dispatch_sdc_unchanged():
    with tempfile.TemporaryDirectory() as workspace:
        sdc, meta = _dispatch_constraints_only(workspace, platform="sky130hd", clock_period_ns=3.5)
        assert "create_clock -period 3.5 " in sdc
        assert meta["sdc_time_unit"] == "ns"
        # ns platforms keep the exact pre-#63 SDC shape (no unit header).
        assert sdc.startswith("set _sc_clk_ports")


def test_asap7_spec_driven_period_converted():
    with tempfile.TemporaryDirectory() as workspace:
        design = os.path.join(workspace, "counter.v")
        _write_file(design, "module counter(input clk, output reg q); always @(posedge clk) q<=~q; endmodule")
        spec = DesignSpec(
            module_name="counter",
            description="counter",
            clock_period_ns=2.0,
            ports=[PortSpec(name="clk", direction="input")],
        )
        save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))
        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=[design],
            top_module="counter",
            platform="asap7",
            clock_period_ns=0,  # no explicit override -> spec-driven branch
            max_stage="constraints",
        )
        final = _poll_final(started["run_id"], workspace)
        assert final is not None and final["status"] == "completed"
        run_dir = os.path.join(workspace, "synth_runs", started["run_id"])
        with open(os.path.join(run_dir, "constraints.sdc"), "r", encoding="utf-8") as f:
            sdc = f.read()
        assert "create_clock -period 2000.0" in sdc
        with open(os.path.join(run_dir, "run_meta.json"), "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["clock_source"] == "spec"
        assert meta["clock_period_ns"] == 2.0
        assert meta["sdc_time_unit"] == "ps"


def test_asap7_metrics_normalized_to_canonical_units():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _make_asap7_run(workspace, NEW_ASAP7_META)

        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        assert result["status"] == "ok"
        m = result["metrics"]
        # ps report values -> ns
        assert m["wns_ns"] == pytest.approx(-0.0274)
        assert m["tns_ns"] == pytest.approx(-2.27618)
        # power is Watts in the report on every platform -> uW/mW unchanged
        assert m["power_uw"] == pytest.approx(3510.0)
        assert m["power_mw"] == pytest.approx(3.51)
        assert m["area_um2"] == pytest.approx(1344.407220)
        # fmax derived from canonical ns on both sides: 1000/(1.2 + 0.0274)
        assert m["fmax_mhz"] == pytest.approx(1000.0 / 1.2274, abs=0.01)

        # The shared finalizer sees the same values.
        summary = sm._compute_summary_metrics(run_dir, NEW_ASAP7_META)
        assert summary["wns_ns"] == pytest.approx(-0.0274)
        assert summary["tns_ns"] == pytest.approx(-2.27618)
        assert summary["fmax_mhz"] == pytest.approx(1000.0 / 1.2274, abs=0.01)


def test_legacy_asap7_run_meta_falls_back_to_the_platform_unit():
    """Runs persisted before the unit fix carry no sdc_time_unit marker — but
    their 6_finish.rpt is still asap7 PICOSECONDS, so a fresh parse of it must
    be normalized by the PLATFORM's unit.

    This assertion used to lock the opposite (values returned RAW). That was
    defensible only while the consumers were sign-only; once _timing_metric_fields
    started deriving worst_slack_ns / clock_period_min_ns / timing_met from these
    numbers, "unscaled" meant publishing ps under an _ns name — 1000x wrong, and
    frozen forever by the schema stamp _ensure_current_summary_metrics writes.
    Issue #63's don't-reinterpret rule still governs STORED values; a fresh parse
    of report text is not one.
    """
    legacy_meta = {k: v for k, v in NEW_ASAP7_META.items() if k != "sdc_time_unit"}
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _make_asap7_run(workspace, legacy_meta)
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        assert result["metrics"]["wns_ns"] == pytest.approx(-0.0274)
        assert result["metrics"]["tns_ns"] == pytest.approx(-2.27618)
        summary = sm._compute_summary_metrics(run_dir, legacy_meta)
        assert summary["wns_ns"] == pytest.approx(-0.0274)


def test_sky130hd_metrics_unchanged():
    sky_meta = dict(NEW_ASAP7_META, platform="sky130hd", sdc_time_unit="ns")
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        base = os.path.join(run_dir, "orfs_reports", "sky130hd", "GCN_core", "base")
        _write_file(os.path.join(base, "6_finish.rpt"), "wns max 0.3391\ntns max 0.00\n")
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(sky_meta))
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        assert result["metrics"]["wns_ns"] == pytest.approx(0.3391)


def test_asap7_cts_summary_normalized():
    with tempfile.TemporaryDirectory() as workspace:
        _make_asap7_run(workspace, NEW_ASAP7_META)
        result = sm.get_cts_summary(workspace=workspace, run_id="synth_0001")
        assert result["status"] == "ok"
        s = result["summary"]
        assert s["clock_period_min_ns"] == pytest.approx(1.17345)
        assert s["worst_slack_ns"] == pytest.approx(0.02655)
        # ORFS prints the fmax line in MHz on every platform — never rescaled.
        assert s["clock_fmax_mhz"] == pytest.approx(852.19)
