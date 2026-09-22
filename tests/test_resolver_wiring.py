"""Per-wrapper wiring of the shared file resolver (command-surface v2, R13/R16).

Each tool that takes a user-supplied file name must resolve it through
``resolve_workspace_file`` — so a basename the UI suggests ('alu.v') reaches a
nested file (rtl/alu.v), everywhere, with one containment and one error
vocabulary. The underlying run functions are monkeypatched to capture exactly
what the wrapper hands them; nothing EDA runs here.
"""
import json
import os

import pytest

pytest.importorskip("langchain_core")

from src.platform_engines.settings import reset_settings_cache
from src.tools import wrappers


@pytest.fixture(autouse=True)
def _self_host(monkeypatch):
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    ws = str(tmp_path)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    return ws


def _mk(ws, rel, content="module alu(input a, output b); endmodule\n"):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# --- lint / sim / synth / cocotb / websim (the compile-set tools) ----------

def test_linter_tool_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/alu.v")
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen["files"] = files
        return {"success": True, "engine": "iverilog", "stderr": "", "diagnostics": []}

    monkeypatch.setattr(wrappers, "run_linter", fake_linter)
    out = wrappers.linter_tool.func(verilog_files=["alu.v"])
    assert "Syntax OK" in out
    assert seen["files"] == [os.path.join(ws, "rtl/alu.v")]


def test_linter_tool_missing_file_pins_does_not_exist(ws):
    out = wrappers.linter_tool.func(verilog_files=["nope.v"])
    assert out.startswith("Error:") and "does not exist" in out


def test_linter_tool_ambiguous_names_candidates(ws):
    _mk(ws, "rtl/alu.v")
    _mk(ws, "given/alu.v")
    out = wrappers.linter_tool.func(verilog_files=["alu.v"])
    assert "Ambiguous" in out and "rtl/alu.v" in out and "given/alu.v" in out


def test_linter_tool_escape_rejected(ws):
    out = wrappers.linter_tool.func(verilog_files=["../evil.v"])
    assert "escapes the workspace" in out


def test_run_simulation_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/alu.v")
    _mk(ws, "tb/alu_tb.v", content="module alu_tb; alu dut(.a(1'b0), .b()); endmodule\n")
    seen = {}

    def fake_sim(**kwargs):
        seen.update(kwargs)
        return {"status": "passed", "simStatus": "test_passed"}

    monkeypatch.setattr(wrappers, "run_sim_isolated", fake_sim)
    out = wrappers.run_simulation.func(
        verilog_files=["alu.v", "alu_tb.v"], sim_top="alu_tb"
    )
    assert json.loads(out)["status"] == "passed"
    # The runner takes workspace-relative paths (tests/test_run_simulation_tool.py
    # pins that an explicit root file reaches it verbatim).
    assert seen["verilog_files"] == ["rtl/alu.v", "tb/alu_tb.v"]


def test_start_synthesis_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/alu.v")
    seen = {}

    def fake_job(**kwargs):
        seen.update(kwargs)
        return {"run_id": "synth_0001", "status": "queued"}

    monkeypatch.setattr(wrappers, "start_synthesis_job", fake_job)
    out = wrappers.start_synthesis.func(verilog_files=["alu.v"], top_module="alu")
    assert json.loads(out)["run_id"] == "synth_0001"
    assert seen["verilog_files"] == [os.path.join(ws, "rtl/alu.v")]


def test_start_synthesis_missing_file_pins_does_not_exist(ws):
    out = wrappers.start_synthesis.func(verilog_files=["nope.v"], top_module="x")
    assert out.startswith("Error:") and "does not exist" in out


def test_cocotb_tool_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/dut.v")
    seen = {}

    def fake_cocotb(files, top, mod, cwd, coverage=False):
        seen["files"] = files
        return {"status": "PASS", "passed": 1, "failed": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(wrappers, "run_cocotb", fake_cocotb)
    out = wrappers.cocotb_tool.func(
        verilog_files=["dut.v"], top_module="dut", python_module="verif.test_dut"
    )
    assert "PASSED" in out
    assert seen["files"] == [os.path.join(ws, "rtl/dut.v")]


def test_cocotb_tool_missing_file_pins_does_not_exist(ws):
    out = wrappers.cocotb_tool.func(
        verilog_files=["nope.v"], top_module="dut", python_module="verif.test_dut"
    )
    assert out.startswith("Error:") and "does not exist" in out


def test_build_interactive_sim_pre_resolves_then_validates(ws, monkeypatch):
    _mk(ws, "rtl/simon.v")
    seen = {}

    def fake_build(files, top, cwd, parameters=None):
        seen["files"] = files
        return {"success": True, "artifact": f"{top}.websim.json", "ports": [], "engine": "native"}

    monkeypatch.setattr(wrappers, "build_websim_netlist", fake_build)
    out = wrappers.build_interactive_sim.func(verilog_files="simon.v", top_module="simon")
    assert "Interactive sim netlist built" in out
    # Resolved to the workspace-relative path — build_websim_netlist's own
    # validation still runs on it (pre-resolution, not a bypass).
    assert seen["files"] == ["rtl/simon.v"]


# --- schematic / waveform / sby / spec -------------------------------------

def test_schematic_tool_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/alu.v")
    seen = {}

    def fake_schematic(abs_file, top, cwd):
        seen["file"] = abs_file
        return {"success": True, "svg_path": "alu.svg"}

    monkeypatch.setattr(wrappers, "generate_schematic", fake_schematic)
    out = wrappers.schematic_tool.func(verilog_file="alu.v", top_module="alu")
    assert "Schematic generated" in out
    assert seen["file"] == os.path.join(ws, "rtl/alu.v")


def test_schematic_tool_missing_pins_does_not_exist(ws):
    out = wrappers.schematic_tool.func(verilog_file="nope.v", top_module="x")
    assert "does not exist" in out


def test_waveform_tool_exact_run_dir_path_still_works(ws, monkeypatch):
    """Run dirs are pruned from the tree scan, but the exact path the run
    record reports (`vcdPath`) is an honest address and resolves as-is."""
    _mk(ws, "sim_runs/sim_0001/dump.vcd", content="$enddefinitions $end\n")
    seen = {}

    def fake_read(abs_file, signals, start_time, end_time):
        seen["file"] = abs_file
        return "ok"

    monkeypatch.setattr(wrappers, "read_waveform", fake_read)
    out = wrappers.waveform_tool.func(
        vcd_file="sim_runs/sim_0001/dump.vcd", signals=["clk"]
    )
    assert out == "ok"
    assert seen["file"] == os.path.join(ws, "sim_runs/sim_0001/dump.vcd")


def test_waveform_tool_escape_rejected(ws):
    out = wrappers.waveform_tool.func(vcd_file="../../etc/passwd", signals=["clk"])
    assert "escapes the workspace" in out


def test_sby_tool_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "verif/fifo.sby", content="[options]\nmode bmc\n")
    seen = {}

    def fake_sby(abs_file, cwd):
        seen["file"] = abs_file
        return {"status": "PASS", "stdout": "", "stderr": ""}

    monkeypatch.setattr(wrappers, "run_sby", fake_sby)
    out = wrappers.sby_tool.func(sby_file="fifo.sby")
    assert "PASSED" in out
    assert seen["file"] == os.path.join(ws, "verif/fifo.sby")


def test_read_spec_resolves_extensionless_name(ws, monkeypatch):
    _mk(ws, "specs/counter_spec.yaml", content="module_name: counter\n")

    class FakeSpec:
        module_name = "counter"

    monkeypatch.setattr(wrappers, "load_yaml_file", lambda p: FakeSpec())
    monkeypatch.setattr(wrappers, "spec_to_prompt", lambda s: "PROMPT")
    out = wrappers.read_spec.func(spec_filename="counter_spec")
    assert "counter" in out and "PROMPT" in out


def test_read_spec_missing_pins_does_not_exist(ws):
    out = wrappers.read_spec.func(spec_filename="nope.yaml")
    assert out.startswith("Error:") and "does not exist" in out


def test_read_spec_never_follows_a_manifest_entry_out_of_the_workspace(tmp_path, monkeypatch):
    """Adversarial-review P1-1, end to end on the real wrapper: a tenant writes
    ``manifest.json`` carrying ``path: ../secret_spec.yaml`` (write_file only
    confines its TARGET and reconcile ignores .json), then asks for the spec by
    basename. The resolver must treat the escaped hit as absent, so the file
    outside the workspace is never opened, parsed, or echoed."""
    import json

    from src.tools.manifest import MANIFEST_FILENAME

    ws = os.path.join(str(tmp_path), "ws")
    os.makedirs(ws)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    _mk(str(tmp_path), "secret_spec.yaml", content="module_name: SECRET_MODULE\n")
    with open(os.path.join(ws, MANIFEST_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"files": [{"name": "secret_spec.yaml", "path": "../secret_spec.yaml", "role": "rtl"}]}, f)

    opened = []
    real_load = wrappers.load_yaml_file
    monkeypatch.setattr(wrappers, "load_yaml_file", lambda p: opened.append(p) or real_load(p))

    for value in ("secret_spec.yaml", "secret_spec"):
        out = wrappers.read_spec.func(spec_filename=value)
        assert out.startswith("Error:") and "does not exist" in out, out
        assert "SECRET_MODULE" not in out and "../secret_spec.yaml" not in out
    assert opened == []


# --- pre-resolution layering: run_python_analysis (R16) ----------------------

def test_run_python_analysis_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "scripts/gen.py", content="print('hi')\n")
    seen = {}

    def fake_run(workspace, script_file, args):
        seen["script"] = script_file
        return {"ok": True, "exit_code": 0}

    import src.tools.run_python as run_python_mod

    monkeypatch.setattr(run_python_mod, "run_python_analysis", fake_run)
    out = wrappers.run_python_analysis.func(script_file="gen.py")
    assert json.loads(out)["ok"] is True
    # Pre-resolution hands run_python the resolved path; its own containment
    # + not-found validation still runs on it.
    assert seen["script"] == "scripts/gen.py"


def test_run_python_analysis_escape_rejected_before_execution(ws):
    out = wrappers.run_python_analysis.func(script_file="../evil.py")
    assert out.startswith("Error:") and "escapes the workspace" in out
