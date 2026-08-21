"""The simulation tool, manifest-driven and explicit-file alike.

There were two sim tools: one compiled the manifest's set into its own
``sim_runs/sim_NNNN/`` directory, the other compiled an explicit file list in
the workspace root where the next run overwrote its VCD. They are one tool now,
and every run is isolated. These tests hold the union: the manifest path is the
default, the explicit file list is still reachable, and the post-synth overrides
the explicit path carried (an explicit netlist, an explicit PDK) still override.

The runner itself is stubbed — the compile/run seam is covered by
tests/test_sim_isolation.py and needs iverilog. What is proven here is what the
tool decides before the runner sees anything.
"""
import json

import pytest

from src.tools import wrappers


DUT = "module counter(input clk, output reg [3:0] q);\nendmodule\n"
TB = "module counter_tb;\ncounter dut(.clk(1'b0));\nendmodule\n"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "counter.v").write_text(DUT, encoding="utf-8")
    (workspace / "counter_tb.v").write_text(TB, encoding="utf-8")
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: str(workspace))
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    return workspace


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        return {"id": "sim_0001", "kind": "sim", "status": "passed",
                "simStatus": "test_passed", "vcdPath": "sim_runs/sim_0001/dump.vcd"}

    monkeypatch.setattr(wrappers, "run_sim_isolated", fake)
    return seen


def _run(**kwargs) -> dict:
    out = wrappers.run_simulation.invoke(kwargs)
    return json.loads(out) if out.startswith("{") else {"error": out}


def test_the_manifest_supplies_the_file_set_by_default(ws, calls):
    res = _run()
    assert res["status"] == "passed"
    assert len(calls) == 1
    assert sorted(calls[0]["verilog_files"]) == ["counter.v", "counter_tb.v"]
    assert calls[0]["top_module"] == "counter_tb"


def test_an_explicit_file_list_overrides_the_manifest(ws, calls):
    """The escape hatch the older tool existed for: compile a set the manifest
    does not describe."""
    (ws / "other_tb.v").write_text(TB.replace("counter_tb", "other_tb"), encoding="utf-8")
    res = _run(verilog_files=["counter.v", "other_tb.v"], sim_top="other_tb")
    assert res["status"] == "passed"
    assert calls[0]["verilog_files"] == ["counter.v", "other_tb.v"]
    assert calls[0]["top_module"] == "other_tb"


def test_an_explicit_list_may_arrive_as_a_json_string(ws, calls):
    """Tool-calling models send a stringified array; the older tool accepted it
    and the bench prompts still tell them to."""
    _run(verilog_files='["counter.v", "counter_tb.v"]', sim_top="counter_tb")
    assert calls[0]["verilog_files"] == ["counter.v", "counter_tb.v"]


def test_a_missing_explicit_file_is_refused_before_the_runner(ws, calls):
    res = _run(verilog_files=["counter.v", "nope.v"], sim_top="counter_tb")
    assert "does not exist" in res["error"]
    assert calls == []


def test_sim_top_falls_back_to_the_manifest(ws, calls):
    _run(verilog_files=["counter.v", "counter_tb.v"])
    assert calls[0]["top_module"] == "counter_tb"


def test_no_top_anywhere_says_how_to_fix_it(ws, calls):
    (ws / "counter_tb.v").unlink()
    (ws / "manifest.json").unlink(missing_ok=True)
    res = _run(verilog_files=["counter.v"])
    assert "simTop" in res["error"] and "update_manifest" in res["error"]
    assert calls == []


def test_an_empty_manifest_set_says_both_ways_out(ws, calls):
    (ws / "counter.v").unlink()
    (ws / "counter_tb.v").unlink()
    (ws / "manifest.json").unlink(missing_ok=True)
    res = _run(sim_top="counter_tb")
    assert "update_manifest" in res["error"] and "verilog_files" in res["error"]
    assert calls == []


# --- post-synth overrides the explicit path carried ---------------------------

def test_an_explicit_netlist_reaches_the_runner(ws, calls):
    _run(mode="post_synth", run_id="synth_0007", netlist_file="custom.v")
    assert calls[0]["mode"] == "post_synth"
    assert calls[0]["run_id"] == "synth_0007"
    assert calls[0]["netlist_file"] == "custom.v"


def test_an_explicit_platform_is_an_override_not_a_fallback(ws, calls):
    """The manifest's platform is design INTENT and may only fill a gap; a
    platform the CALLER names pins the stdcell set. Passing intent as an
    override would link an asap7 netlist against sky130 models."""
    _run(mode="post_synth", platform="asap7")
    assert calls[0]["platform_override"] == "asap7"
    # ...and the manifest's own platform still travels as the fallback only.
    assert calls[0]["platform"] == "sky130hd"


def test_without_a_platform_argument_only_intent_is_forwarded(ws, calls):
    _run(mode="post_synth")
    assert calls[0]["platform_override"] is None
    assert calls[0]["platform"]  # the manifest's platform, as a fallback


def test_the_pass_marker_and_profile_are_forwarded(ws, calls):
    _run(sim_profile="pinned", pass_marker="ALL GOOD")
    assert calls[0]["sim_profile"] == "pinned"
    assert calls[0]["pass_marker"] == "ALL GOOD"


# --- what the reply leads with ------------------------------------------------

def test_a_duplicate_module_in_the_compile_set_leads_the_reply(ws, calls):
    """The collision warning fronted the manifest-driven reply and must front
    the explicit one too — a run is where a duplicate module costs something."""
    (ws / "copy_of_counter.v").write_text(DUT, encoding="utf-8")
    res = _run(verilog_files=["counter.v", "copy_of_counter.v", "counter_tb.v"],
               sim_top="counter_tb")
    assert list(res)[0] == "manifestWarnings"
    assert res["id"] == "sim_0001"
