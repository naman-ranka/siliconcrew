import os

from src.tools.synthesis_manager import get_route_drc_summary


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "route_drc_workspace")


def test_get_route_drc_summary_handles_empty_report_as_clean():
    workspace = _fixture_workspace()
    result = get_route_drc_summary(workspace=workspace, run_id="synth_0005")

    assert result["status"] == "ok"
    assert result["clean"] is True
    assert result["route_stage_status"] == "completed"
    assert result["violation_count"] == 0
    assert result["unique_violation_count"] == 0
    assert "completed route stage" in result["notes"][0]


def test_get_route_drc_summary_does_not_treat_empty_incomplete_report_as_clean(tmp_path):
    workspace = str(tmp_path)
    report_dir = os.path.join(workspace, "synth_runs", "synth_0007", "orfs_reports", "sky130hd", "demo_top", "base")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
        f.write("synth_0007")
    with open(os.path.join(workspace, "synth_runs", "synth_0007", "run_meta.json"), "w", encoding="utf-8") as f:
        f.write('{"run_id": "synth_0007", "top_module": "demo_top", "platform": "sky130hd"}')
    with open(os.path.join(report_dir, "5_route_drc.rpt"), "w", encoding="utf-8") as f:
        f.write("")

    result = get_route_drc_summary(workspace=workspace, run_id="synth_0007")

    assert result["status"] == "ok"
    assert result["clean"] is False
    assert result["route_stage_status"] == "pending"
    assert "not treated as clean" in result["notes"][0]


def test_get_route_drc_summary_counts_nonempty_lines():
    workspace = _fixture_workspace()
    result = get_route_drc_summary(workspace=workspace, run_id="synth_0006")

    assert result["status"] == "ok"
    assert result["clean"] is False
    assert result["violation_count"] == 3
    assert result["unique_violation_count"] == 2
    assert result["sample_violations"][0] == "Short met1 segment near u1"
