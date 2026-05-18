import os

from src.tools.synthesis_manager import get_route_drc_summary


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "route_drc_workspace")


def test_get_route_drc_summary_handles_empty_report_as_clean():
    workspace = _fixture_workspace()
    result = get_route_drc_summary(workspace=workspace, run_id="synth_0005")

    assert result["status"] == "ok"
    assert result["clean"] is True
    assert result["violation_count"] == 0
    assert result["unique_violation_count"] == 0
    assert "Empty 5_route_drc.rpt" in result["notes"][0]


def test_get_route_drc_summary_counts_nonempty_lines():
    workspace = _fixture_workspace()
    result = get_route_drc_summary(workspace=workspace, run_id="synth_0006")

    assert result["status"] == "ok"
    assert result["clean"] is False
    assert result["violation_count"] == 3
    assert result["unique_violation_count"] == 2
    assert result["sample_violations"][0] == "Short met1 segment near u1"
