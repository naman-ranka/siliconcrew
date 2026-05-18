import os

from src.tools.synthesis_manager import get_congestion_summary


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "congestion_workspace")


def test_get_congestion_summary_parses_layer_rows_and_total():
    workspace = _fixture_workspace()
    result = get_congestion_summary(workspace=workspace, run_id="synth_0008")

    assert result["status"] == "ok"
    assert result["artifact_scope"] == "orfs_logs"
    assert result["layer_count"] == 6
    assert result["layers"][1]["layer"] == "met1"
    assert result["layers"][1]["resource"] == 873
    assert result["layers"][1]["demand"] == 16
    assert result["layers"][1]["usage_pct"] == 1.83
    assert result["total"]["resource"] == 2643
    assert result["total"]["demand"] == 45
    assert result["total"]["usage_pct"] == 1.70


def test_get_congestion_summary_reports_overflow_and_wire_stats():
    workspace = _fixture_workspace()
    result = get_congestion_summary(workspace=workspace, run_id="synth_0008")

    assert result["status"] == "ok"
    assert result["has_overflow"] is False
    assert result["congested_layers"] == []
    assert result["wirelength_um"] == 503.0
    assert result["routed_nets"] == 24
