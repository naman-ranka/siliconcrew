"""One stage reader, four readers' worth of answers.

``get_cts_summary``, ``get_congestion_summary``, ``get_route_drc_summary`` and
``read_stage_report`` took the same argument, resolved the run the same way, and
each answered about one stage. They are one tool keyed by stage now. These tests
run it against the same fixture workspaces the four separate tests used, so what
is proven is that the merged tool returns the SAME parse — not merely that it
returns something.

The reply always says which view it gave back, because three of the six stages
have no parser and asking for a summary there gets the artifact.
"""
import json
import os

import pytest

from src.tools import wrappers


def _fixture(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


@pytest.fixture
def workspace(monkeypatch):
    def _use(name: str) -> str:
        path = _fixture(name)
        monkeypatch.setattr(wrappers, "get_workspace_path", lambda: path)
        return path

    return _use


def _read(**kwargs) -> dict:
    return json.loads(wrappers.read_stage_report.invoke(kwargs))


# --- the three parsed stages --------------------------------------------------

def test_cts_returns_the_clock_tree_parse(workspace):
    workspace("cts_workspace")
    res = _read(stage="cts", run_id="synth_0007")
    assert res["status"] == "ok" and res["view"] == "summary"
    assert res["stage"] == "cts"
    assert res["summary"]["wns_ns"] == -0.09
    assert res["summary"]["clock_fmax_mhz"] == 1445.99
    assert res["summary"]["max_fanout_violation_count"] == 1


def test_grt_returns_the_congestion_parse(workspace):
    workspace("congestion_workspace")
    res = _read(stage="grt", run_id="synth_0008")
    assert res["status"] == "ok" and res["view"] == "summary"
    assert res["stage"] == "grt"
    assert res["layer_count"] == 6
    assert res["total"]["usage_pct"] == 1.70
    assert res["has_overflow"] is False


def test_route_returns_the_drc_parse(workspace):
    workspace("route_drc_workspace")
    res = _read(stage="route", run_id="synth_0005")
    assert res["status"] == "ok" and res["view"] == "summary"
    assert res["stage"] == "route"
    assert res["clean"] is True
    assert res["route_stage_status"] == "completed"
    assert res["violation_count"] == 0


def test_a_parsed_stage_can_still_hand_back_its_artifact(workspace):
    """`raw` is why the artifact reader survived alongside the summaries: when
    the parse does not carry the detail, read the report itself."""
    workspace("route_drc_workspace")
    res = _read(stage="route", run_id="synth_0005", view="raw")
    assert res["view"] == "raw"
    assert res["artifact_name"] == "5_route_drc.rpt"
    assert "content_excerpt" in res


# --- the three stages with no parser -----------------------------------------

def test_floorplan_answers_with_its_artifact_and_says_so(workspace):
    workspace("stage_report_workspace")
    res = _read(stage="floorplan", run_id="synth_0003")
    assert res["status"] == "ok"
    assert res["view"] == "raw"          # asked for summary, got raw...
    assert "No structured summary" in res["note"]   # ...and the reply says why
    assert res["artifact_name"] == "2_floorplan_final.rpt"
    assert "floorplan summary" in res["content_excerpt"]


def test_place_reads_the_placement_log(workspace):
    workspace("stage_report_workspace")
    res = _read(stage="place", run_id="synth_0004")
    assert res["status"] == "ok" and res["view"] == "raw"
    assert res["artifact_scope"] == "orfs_logs"
    assert res["artifact_name"] == "3_3_place_gp.json"
    assert '"overflow":0' in res["content_excerpt"]


def test_asking_for_raw_on_an_unparsed_stage_adds_no_note(workspace):
    """The note explains a substitution. Asking for what you got is not one."""
    workspace("stage_report_workspace")
    res = _read(stage="floorplan", run_id="synth_0003", view="raw")
    assert res["view"] == "raw"
    assert "note" not in res


# --- resolution is shared ------------------------------------------------------

def test_an_unknown_run_is_an_error_on_every_stage(workspace):
    workspace("cts_workspace")
    for stage in ("cts", "grt", "route", "floorplan"):
        res = _read(stage=stage, run_id="synth_9999")
        assert res["status"] == "error", stage
        assert "not found" in res["message"], stage
