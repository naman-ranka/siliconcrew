"""Interactive web-sim netlist builder (Phase 0).

The yosys run is faked (no EDA binaries in CI); what's under test is the
artifact contract: containment, provenance hashing, port extraction, honest
errors, and catalog policy flags.
"""
import hashlib
import json
import os

import pytest

from src.tools import build_interactive_sim as bis


COUNTER_NETLIST = {
    "creator": "Yosys (fake)",
    "modules": {
        "counter": {
            "ports": {
                "clk": {"direction": "input", "bits": [2]},
                "rst_n": {"direction": "input", "bits": [3]},
                "en": {"direction": "input", "bits": [4]},
                "count": {"direction": "output", "bits": [5, 6, 7, 8]},
            },
            "cells": {},
            "netnames": {},
        }
    },
}


@pytest.fixture
def fake_yosys(monkeypatch):
    """Pretend a native yosys ran and wrote COUNTER_NETLIST to the -p output."""
    calls = []

    def _fake_run(script, cwd, engine):
        calls.append({"script": script, "cwd": cwd, "engine": engine})
        out = script.rsplit("write_json ", 1)[1]
        with open(os.path.join(cwd, out), "w") as f:
            json.dump(COUNTER_NETLIST, f)
        return {"success": True, "stderr": ""}

    monkeypatch.setattr(bis, "pick_engine", lambda: {"engine": "native"})
    monkeypatch.setattr(bis, "_run_yosys", _fake_run)
    return calls


def _write_source(ws, name="counter.v", body="module counter; endmodule\n"):
    path = os.path.join(ws, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(body)
    return path


def test_happy_path_artifact_contract(tmp_path, fake_yosys):
    ws = str(tmp_path)
    src = _write_source(ws)

    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)

    assert result["success"], result
    assert result["artifact"] == "counter.websim.json"
    assert result["engine"] == "native"

    with open(os.path.join(ws, result["artifact"])) as f:
        payload = json.load(f)
    assert payload["format"] == bis.ARTIFACT_FORMAT
    assert payload["top"] == "counter"
    assert payload["yosys_netlist"] == COUNTER_NETLIST
    # provenance = sha256 of source BYTES (content hash, never mtime)
    with open(src, "rb") as f:
        expected = hashlib.sha256(f.read()).hexdigest()
    assert payload["sources"] == {"counter.v": expected}
    # aware-UTC timestamp
    assert payload["generated_at"].endswith("+00:00")
    # ports extracted with widths
    ports = {p["name"]: p for p in payload["ports"]}
    assert ports["count"] == {"name": "count", "direction": "output", "bits": 4}
    assert ports["clk"]["direction"] == "input"
    # the temp netlist never survives
    assert not [p for p in os.listdir(ws) if p.endswith(".tmp.json")]


def test_ports_returned_to_caller_match_artifact(tmp_path, fake_yosys):
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    assert {p["name"] for p in result["ports"]} == {"clk", "rst_n", "en", "count"}


def test_subdir_source_stays_contained(tmp_path, fake_yosys):
    ws = str(tmp_path)
    _write_source(ws, "rtl/counter.v")
    result = bis.build_websim_netlist(["rtl/counter.v"], "counter", cwd=ws)
    assert result["success"]
    with open(os.path.join(ws, "counter.websim.json")) as f:
        assert "rtl/counter.v" in json.load(f)["sources"]


def test_traversal_and_absolute_paths_rejected(tmp_path, fake_yosys):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    outside = _write_source(str(tmp_path), "evil.v")

    for attempt in ["../evil.v", outside]:
        result = bis.build_websim_netlist([attempt], "counter", cwd=ws)
        assert not result["success"]
    assert not fake_yosys  # engine never invoked


def test_hostile_filename_and_module_rejected(tmp_path, fake_yosys):
    ws = str(tmp_path)
    result = bis.build_websim_netlist(["a.v; delete -all"], "counter", cwd=ws)
    assert not result["success"] and "characters" in result["error"]
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "counter; evil", cwd=ws)
    assert not result["success"] and "top module" in result["error"]
    assert not fake_yosys


def test_missing_file_is_honest(tmp_path, fake_yosys):
    result = bis.build_websim_netlist(["nope.v"], "counter", cwd=str(tmp_path))
    assert not result["success"] and "does not exist" in result["error"]


def test_no_engine_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(bis, "pick_engine", lambda: {"error": "yosys is not installed on this instance."})
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    assert not result["success"] and "yosys" in result["error"]


def test_wrong_top_module_lists_available(tmp_path, fake_yosys):
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "not_there", cwd=ws)
    assert not result["success"] and "counter" in result["error"]


def test_yosys_failure_surfaces_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(bis, "pick_engine", lambda: {"engine": "native"})
    monkeypatch.setattr(
        bis, "_run_yosys", lambda script, cwd, engine: {"success": False, "stderr": "ERROR: syntax error"}
    )
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    assert not result["success"] and "syntax error" in result["error"]


def test_docker_engine_runs_in_the_workspace_mount(tmp_path, monkeypatch):
    """Regression: the yosys script uses workspace-relative paths, but
    run_docker_command's default container cwd is /OpenROAD-flow-scripts/flow.
    The docker branch must run inside the /workspace mount or every read/write
    misses the workspace."""
    ws = str(tmp_path)
    _write_source(ws)
    calls = []

    def fake_docker(command, workspace_path=None, cwd=None, **kwargs):
        calls.append({"command": command, "workspace_path": workspace_path, "cwd": cwd})
        # Simulate yosys running IN the mount: the relative write_json target
        # must land in the host workspace.
        out = command.rsplit("write_json ", 1)[1].rstrip("'")
        with open(os.path.join(workspace_path, out), "w") as f:
            json.dump(COUNTER_NETLIST, f)
        return {"success": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(bis, "pick_engine", lambda: {"engine": "docker"})
    monkeypatch.setattr("src.tools.run_docker.run_docker_command", fake_docker)

    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    assert result["success"], result
    assert result["engine"] == "docker"
    assert calls[0]["cwd"] == "/workspace"
    assert calls[0]["workspace_path"] == ws


def test_yosys_script_handles_inferred_memories(tmp_path, fake_yosys):
    """Regression: the browser engine rejects raw $memrd/$memwr pairs, and its
    $mem cell breaks on ABITS=32 (a 32-bit literal index like `seq[0] <= x`
    widens the collected address). The script must wreduce THEN collect
    memories so designs like simon_game simulate at all."""
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    assert result["success"]
    script = fake_yosys[0]["script"]
    assert "wreduce; memory -nomap" in script
    # narrowing must happen BEFORE collection or ABITS is already frozen
    assert script.index("wreduce") < script.index("memory -nomap")


def test_parameter_overrides_elaborate_and_are_recorded(tmp_path, fake_yosys):
    """Timing-constant overrides (TICKS_PER_MILLI/CLK_FREQ idiom): passed to
    yosys as `hierarchy -chparam` and recorded verbatim in the artifact so the
    provenance strip can show the sim is NOT the source defaults."""
    ws = str(tmp_path)
    _write_source(ws)
    result = bis.build_websim_netlist(
        ["counter.v"], "counter", cwd=ws, parameters={"TICKS_PER_MILLI": 1}
    )
    assert result["success"], result
    assert "hierarchy -chparam TICKS_PER_MILLI 1 -top counter" in fake_yosys[0]["script"]
    with open(os.path.join(ws, "counter.websim.json")) as f:
        assert json.load(f)["parameters"] == {"TICKS_PER_MILLI": 1}

    # no overrides → no parameters key (v1 artifacts stay byte-identical)
    result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws)
    with open(os.path.join(ws, "counter.websim.json")) as f:
        assert "parameters" not in json.load(f)


def test_hostile_parameter_names_and_values_rejected(tmp_path, fake_yosys):
    ws = str(tmp_path)
    _write_source(ws)
    for params in [{"P; delete -all": 1}, {"CLK_FREQ": "50; evil"}, {"CLK_FREQ": True}]:
        result = bis.build_websim_netlist(["counter.v"], "counter", cwd=ws, parameters=params)
        assert not result["success"], params
    assert not fake_yosys  # engine never invoked


def test_catalog_policy_flags():
    from src.api import tool_catalog as tc

    assert tc.category_of("build_interactive_sim") == "verification"
    assert "build_interactive_sim" in tc.PROTECTED_TOOLS
    assert "build_interactive_sim" in tc.MUTATING_TOOLS
    assert "build_interactive_sim" not in tc.ASYNC_TOOLS
    assert "build_interactive_sim" not in tc.EXCLUDED_FROM_UI


def test_registered_in_single_tool_registry():
    from src.tools.wrappers import mcp_tools

    assert "build_interactive_sim" in {t.name for t in mcp_tools}
