import os

from src.tools.synthesis_manager import read_stage_report


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "stage_report_workspace")


def test_read_stage_report_reads_floorplan_report():
    workspace = _fixture_workspace()
    report = read_stage_report(workspace=workspace, run_id="synth_0003", stage="floorplan")

    assert report["status"] == "ok"
    assert report["stage"] == "floorplan"
    assert report["artifact_name"] == "2_floorplan_final.rpt"
    assert "floorplan summary" in report["content_excerpt"]
    assert report["content_truncated"] is False


def test_read_stage_report_reads_place_log():
    workspace = _fixture_workspace()
    report = read_stage_report(workspace=workspace, run_id="synth_0004", stage="place")

    assert report["status"] == "ok"
    assert report["artifact_scope"] == "orfs_logs"
    assert report["artifact_name"] == "3_3_place_gp.json"
    assert "\"overflow\":0" in report["content_excerpt"]
