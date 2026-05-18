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
