"""Per-wrapper wiring of the shared file resolver (W1, amendments A1-A7).

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

    def fake_linter(files, cwd, engine="auto"):
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


def test_simulation_tool_resolves_nested_basename(ws, monkeypatch):
    _mk(ws, "rtl/alu.v")
    _mk(ws, "tb/alu_tb.v")
    seen = {}

    def fake_sim(**kwargs):
        seen.update(kwargs)
        return {"status": "test_passed"}

    monkeypatch.setattr(wrappers, "run_simulation", fake_sim)
    out = wrappers.simulation_tool.func(
        verilog_files=["alu.v", "alu_tb.v"], top_module="alu_tb"
    )
    assert json.loads(out)["status"] == "test_passed"
    assert seen["verilog_files"] == [
        os.path.join(ws, "rtl/alu.v"),
        os.path.join(ws, "tb/alu_tb.v"),
    ]


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

    def fake_cocotb(files, top, mod, cwd):
        seen["files"] = files
        return {"status": "PASS", "passed": 1, "failed": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(wrappers, "run_cocotb", fake_cocotb)
    out = wrappers.cocotb_tool.func(
        verilog_files=["dut.v"], top_module="dut", python_module="verif.test_dut"
    )
    assert json.loads(out)["status"] == "test_passed"
    assert seen["files"] == [os.path.join(ws, "rtl/dut.v")]


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


def test_waveform_tool_accepts_bare_sim_run_id(ws, monkeypatch):
    _mk(ws, "sim_runs/sim_0003/counter_tb.vcd", content="$enddefinitions $end\n")
    seen = {}

    def fake_read(abs_file, signals, start_time, end_time):
        seen["file"] = abs_file
        return "waveform"

    monkeypatch.setattr(wrappers, "read_waveform", fake_read)
    out = wrappers.waveform_tool.func(vcd_file="sim_0003", signals=["clk"])
    assert out == "waveform"
    assert seen["file"] == os.path.join(ws, "sim_runs/sim_0003/counter_tb.vcd")


def test_waveform_tool_run_id_without_vcd_is_honest(ws):
    os.makedirs(os.path.join(ws, "sim_runs", "sim_0004"))
    out = wrappers.waveform_tool.func(vcd_file="sim_0004", signals=["clk"])
    assert out.startswith("Error:") and "no VCD" in out


def test_waveform_tool_unknown_run_id_is_honest(ws):
    out = wrappers.waveform_tool.func(vcd_file="sim_0099", signals=["clk"])
    assert out.startswith("Error:") and "does not exist" in out


def test_waveform_tool_exact_run_dir_path_still_works(ws, monkeypatch):
    _mk(ws, "sim_runs/sim_0001/dump.vcd", content="$enddefinitions $end\n")
    seen = {}
    monkeypatch.setattr(
        wrappers, "read_waveform",
        lambda abs_file, signals, start_time, end_time: seen.setdefault("file", abs_file) and "" or "ok",
    )
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


# --- pre-resolution layering: python + XLS families (A1) --------------------

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


def test_dslx_interpreter_resolves_extensionless_name(ws, monkeypatch):
    _mk(ws, "kernels/sat_add.x", content="fn main() {}\n")
    seen = {}

    import src.tools.run_xls as run_xls_mod

    def fake_interp(filename, cwd):
        seen["file"] = filename
        return {"success": True, "stage": "interpreter", "stdout": "", "stderr": "", "command": ""}

    monkeypatch.setattr(run_xls_mod, "run_dslx_interpreter", fake_interp)
    out = wrappers.run_dslx_interpreter.func(filename="sat_add")
    assert json.loads(out)["success"] is True
    assert seen["file"] == "kernels/sat_add.x"


def test_dslx_interpreter_missing_is_structured_failure(ws):
    out = json.loads(wrappers.run_dslx_interpreter.func(filename="nope.x"))
    assert out["success"] is False
    assert out["stage"] == "interpreter"
    assert "does not exist" in out["stderr"]


def test_optimize_xls_ir_resolves_basename(ws, monkeypatch):
    _mk(ws, "build/sat_add.ir", content="package sat_add\n")
    seen = {}

    import src.tools.run_xls as run_xls_mod

    def fake_opt(ir_filename, cwd):
        seen["file"] = ir_filename
        return {"success": True, "stage": "optimization", "stdout": "", "stderr": "", "command": ""}

    monkeypatch.setattr(run_xls_mod, "optimize_xls_ir", fake_opt)
    out = wrappers.optimize_xls_ir.func(ir_filename="sat_add.ir")
    assert json.loads(out)["success"] is True
    assert seen["file"] == "build/sat_add.ir"


def test_codegen_xls_resolves_opt_ir_stem(ws, monkeypatch):
    _mk(ws, "build/sat_add.opt.ir", content="package sat_add\n")
    seen = {}

    import src.tools.run_xls as run_xls_mod

    def fake_codegen(**kwargs):
        seen.update(kwargs)
        return {"success": True, "stage": "codegen", "stdout": "", "stderr": "", "command": ""}

    monkeypatch.setattr(run_xls_mod, "codegen_xls", fake_codegen)
    out = wrappers.codegen_xls.func(opt_ir_filename="sat_add.opt")
    assert json.loads(out)["success"] is True
    assert seen["opt_ir_filename"] == "build/sat_add.opt.ir"


# --- the fence: load_yaml_spec_file keeps its project-root fallback (A4) ----

def test_load_yaml_spec_file_project_root_fallback_not_resolver_gated(ws):
    """A workspace-missing relative path must still fall through to the
    PROJECT ROOT lookup (bundled hackathon problems live outside the
    workspace) — the resolver's containment must not intercept it."""
    out = wrappers.load_yaml_spec_file.func(yaml_path="problems/nope_spec.yaml")
    # The historic message names the PROJECT-ROOT path it last tried — proof
    # the fallback ran instead of the resolver's workspace-only error.
    assert "YAML file not found at" in out
    assert "problems/nope_spec.yaml" in out
    assert "searched the manifest" not in out
