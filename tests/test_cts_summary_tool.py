import os

from src.tools.synthesis_manager import get_cts_summary


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "cts_workspace")


def test_get_cts_summary_parses_core_numeric_fields():
    workspace = _fixture_workspace()
    result = get_cts_summary(workspace=workspace, run_id="synth_0007")

    assert result["status"] == "ok"
    assert result["clock_names"] == ["clk"]
    assert result["summary"]["wns_ns"] == -0.09
    assert result["summary"]["tns_ns"] == -0.13
    assert result["summary"]["worst_slack_ns"] == -0.09
    assert result["summary"]["clock_period_min_ns"] == 0.69
    assert result["summary"]["clock_fmax_mhz"] == 1445.99
    assert result["summary"]["setup_skew_ns"] == -0.0


def test_get_cts_summary_parses_violation_and_path_fields():
    workspace = _fixture_workspace()
    result = get_cts_summary(workspace=workspace, run_id="synth_0007")

    assert result["status"] == "ok"
    assert result["summary"]["max_slew_violation_count"] == 0
    assert result["summary"]["max_fanout_violation_count"] == 1
    assert result["summary"]["max_cap_violation_count"] == 0
    assert result["summary"]["setup_violation_count"] == 2
    assert result["summary"]["hold_violation_count"] == 0
    assert result["summary"]["critical_path_delay_ns"] == 0.83
    assert result["summary"]["critical_path_slack_ns"] == -0.09
    assert result["summary"]["slack_over_delay_ratio"] == -0.1084
    assert result["startpoint_count"] == 2
    assert result["endpoint_count"] == 2
    assert result["sample_startpoints"][0].startswith("state[4]")


def test_cts_period_min_sentinel_is_not_a_metric(tmp_path):
    """Same OpenSTA sentinel the finish path nulls: 'period_min = 0.00
    fmax = inf' means no reg-to-reg path — 0.0 published as a real minimum
    period reads as infinite achievable frequency, one MCP tool away from the
    surface that was fixed."""
    import json as _json
    from src.tools import synthesis_manager as _sm

    ws = str(tmp_path)
    run_dir = os.path.join(ws, "synth_runs", "synth_0001")
    rpt = os.path.join(run_dir, "orfs_reports", "sky130hd", "and2", "base", "4_cts_final.rpt")
    os.makedirs(os.path.dirname(rpt), exist_ok=True)
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("wns max 0.00\ntns max 0.00\nclk period_min = 0.00 fmax = inf\n0.0123 setup skew\n")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        _json.dump({"run_id": "synth_0001", "status": "completed", "platform": "sky130hd",
                    "top_module": "and2", "sdc_time_unit": "ns"}, f)
    with open(os.path.join(ws, "synth_runs", "index.json"), "w", encoding="utf-8") as f:
        _json.dump({"runs": [{"run_id": "synth_0001", "status": "completed"}], "latest": "synth_0001"}, f)

    out = _sm.get_cts_summary(ws, "synth_0001")
    assert out["status"] == "ok"
    assert out["summary"]["clock_period_min_ns"] is None
    assert out["summary"]["clock_fmax_mhz"] is None
