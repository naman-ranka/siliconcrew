import os
import tempfile

from src.tools import run_simulation as rs
from src.tools import sim_manager as sm


def test_simulation_requires_explicit_pass_marker(monkeypatch):
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "PASS generic\n", "stderr": "", "command": "vvp"})

    result = rs.run_simulation(verilog_files=[], top_module="tb", mode="rtl", pass_marker="TEST PASSED")
    assert result["status"] == "test_failed"
    assert result["pass_marker_found"] is False


def test_near_miss_pass_marker_reports_grepped_marker(monkeypatch):
    """F11: a TB that prints "ALL TESTS PASSED" (but not the exact grepped
    substring "TEST PASSED") is honestly test_failed, and the result carries
    the exact marker that was searched for so the UI can explain the miss."""
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "ALL TESTS PASSED\n", "stderr": "", "command": "vvp"})

    result = rs.run_simulation(verilog_files=[], top_module="tb", mode="rtl", pass_marker="TEST PASSED")
    assert result["status"] == "test_failed"
    assert result["pass_marker_found"] is False
    assert result["pass_marker"] == "TEST PASSED"


def test_sim_run_meta_persists_grepped_pass_marker(monkeypatch):
    """F11: the SimRun run_meta records the exact grepped marker beside
    passMarkerFound, so the failed run stays self-describing on disk."""
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "ALL TESTS PASSED\n", "stderr": "", "command": "vvp"})

    with tempfile.TemporaryDirectory() as workspace:
        tb = os.path.join(workspace, "tb.v")
        open(tb, "w", encoding="utf-8").write("module tb; endmodule")

        sim_run = sm.run_sim_isolated(
            workspace=workspace,
            verilog_files=[tb],
            top_module="tb",
            mode="rtl",
            pass_marker="TEST PASSED",
        )

        assert sim_run["status"] == "failed"
        assert sim_run["passMarkerFound"] is False
        assert sim_run["passMarker"] == "TEST PASSED"

        persisted = sm.get_sim_run(workspace, sim_run["id"])
        assert persisted["passMarker"] == "TEST PASSED"


def test_simulation_compile_failed_reports_unresolved_cells(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        os.makedirs(run_dir, exist_ok=True)
        netlist = os.path.join(run_dir, "netlist.v")
        tb = os.path.join(workspace, "tb.v")
        stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "dummy.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(netlist, "w", encoding="utf-8").write("module top; endmodule")
        open(tb, "w", encoding="utf-8").write("module tb; endmodule")
        open(stdcell, "w", encoding="utf-8").write("module dummy; endmodule")

        monkeypatch.setattr(rs, "get_run_dir", lambda cwd, run_id: run_dir)
        monkeypatch.setattr(rs, "resolve_stdcell_models", lambda workspace, platform: ([stdcell], {"updated_at": "now", "files": []}))
        monkeypatch.setattr(
            rs,
            "_compile",
            lambda **kwargs: {
                "returncode": 1,
                "stdout": "",
                "stderr": "Unknown module type: NAND2X1\nmodule INVX1 is undefined",
                "command": "iverilog",
            },
        )

        result = rs.run_simulation(
            verilog_files=[tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            run_id="synth_0001",
            netlist_file=netlist,
            platform="asap7",
        )

        assert result["status"] == "compile_failed"
        assert "NAND2X1" in result["unresolved_cells"]
        assert "INVX1" in result["unresolved_cells"]


def test_simulation_output_budget(monkeypatch):
    big = "\n".join(f"line{i}" for i in range(200))
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": big + "\nTEST PASSED", "stderr": big, "command": "vvp"})

    result = rs.run_simulation(verilog_files=[], top_module="tb", mode="rtl")
    assert result["status"] == "test_passed"
    assert result["log_truncated"] is True
    assert len(result["stdout_tail"]) <= 4000
    assert len(result["stderr_tail"]) <= 4000


def test_simulation_failure_type_assertion(monkeypatch):
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(
        rs,
        "_simulate",
        lambda **kwargs: {"returncode": 1, "stdout": "ASSERTION FAILED at cycle 12\n", "stderr": "", "command": "vvp"},
    )

    result = rs.run_simulation(verilog_files=[], top_module="tb", mode="rtl")
    assert result["status"] == "sim_failed"
    assert result["failure_type"] == "assertion"
    assert "assertion failed" in (result["first_failure_line"] or "").lower()


def test_post_synth_missing_cache_includes_bootstrap_hint(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        netlist = os.path.join(workspace, "netlist.v")
        tb = os.path.join(workspace, "tb.v")
        open(netlist, "w", encoding="utf-8").write("module top; endmodule")
        open(tb, "w", encoding="utf-8").write("module tb; top u0(); endmodule")

        monkeypatch.setattr(
            rs,
            "resolve_stdcell_models",
            lambda workspace_arg, platform_arg: (_ for _ in ()).throw(
                FileNotFoundError("Standard-cell cache missing for platform 'asap7'.")
            ),
        )

        result = rs.run_simulation(
            verilog_files=[tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            netlist_file=netlist,
            platform="asap7",
        )

        assert result["status"] == "compile_failed"
        assert "bootstrap_stdcells.py" in result["stderr_tail"]
        assert "First-Run Standard-Cell Bootstrap" in result["stderr_tail"]


def test_post_synth_asap7_compat_profile_uses_compat_selection(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        netlist = os.path.join(workspace, "netlist.v")
        tb = os.path.join(workspace, "tb.v")
        stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "dummy.v")
        compat_stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "compat_dff.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(netlist, "w", encoding="utf-8").write("module top; endmodule")
        open(tb, "w", encoding="utf-8").write("module tb; top u0(); endmodule")
        open(stdcell, "w", encoding="utf-8").write("module dummy; endmodule")
        open(compat_stdcell, "w", encoding="utf-8").write("module compat_dff; endmodule")

        monkeypatch.setattr(rs, "resolve_stdcell_models", lambda workspace_arg, platform_arg: ([stdcell], {"files": []}))
        monkeypatch.setattr(rs, "_asap7_compat_stdcell_files", lambda stdcells, netlist_path: [compat_stdcell])

        captured = {}

        def fake_compile(**kwargs):
            captured["compile_files"] = kwargs["compile_files"]
            return {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"}

        monkeypatch.setattr(rs, "_compile", fake_compile)
        monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            netlist_file=netlist,
            platform="asap7",
            sim_profile="compat",
        )

        assert result["status"] == "test_passed"
        assert result["sim_profile"] == "compat"
        assert compat_stdcell in captured["compile_files"]


def test_post_synth_asap7_auto_profile_defaults_to_compat(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        netlist = os.path.join(workspace, "netlist.v")
        tb = os.path.join(workspace, "tb.v")
        stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "dummy.v")
        compat_stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "compat_dff.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(netlist, "w", encoding="utf-8").write("module top; endmodule")
        open(tb, "w", encoding="utf-8").write("module tb; top u0(); endmodule")
        open(stdcell, "w", encoding="utf-8").write("module dummy; endmodule")
        open(compat_stdcell, "w", encoding="utf-8").write("module compat_dff; endmodule")

        monkeypatch.setattr(rs, "resolve_stdcell_models", lambda workspace_arg, platform_arg: ([stdcell], {"files": []}))
        monkeypatch.setattr(rs, "_asap7_compat_stdcell_files", lambda stdcells, netlist_path: [compat_stdcell])
        monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
        monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            netlist_file=netlist,
            platform="asap7",
            sim_profile="auto",
        )

        assert result["status"] == "test_passed"
        assert result["sim_profile"] == "compat"


def test_find_netlist_resolves_orfs_gate_netlist_not_inputs_rtl():
    """#51: with both orfs_results/**/6_final.v (gate netlist) and inputs/<top>.v
    (pre-synthesis RTL) present, _find_netlist resolves the gate netlist — never
    the RTL input, which would double-declare the design module in post_synth."""
    from src.tools.synthesis_manager import _find_netlist

    with tempfile.TemporaryDirectory() as run_dir:
        gate_dir = os.path.join(run_dir, "orfs_results", "sky130hd", "top", "base")
        os.makedirs(gate_dir, exist_ok=True)
        gate = os.path.join(gate_dir, "6_final.v")
        open(gate, "w", encoding="utf-8").write("module top(); endmodule // gate\n")

        inputs_dir = os.path.join(run_dir, "inputs")
        os.makedirs(inputs_dir, exist_ok=True)
        rtl = os.path.join(inputs_dir, "top.v")
        # RTL input name-matches the top module — the exact A15 trap. It must
        # never be resolved as the netlist.
        open(rtl, "w", encoding="utf-8").write("module top(); endmodule // rtl\n")

        resolved = _find_netlist(run_dir, "top")
        assert resolved == gate
        assert "inputs" not in os.path.relpath(resolved, run_dir).split(os.sep)


def test_find_netlist_returns_none_without_orfs_results():
    """#51: no synthesized netlist under orfs_results/ resolves to None (caller
    errors cleanly) rather than falling back to an inputs/ RTL source."""
    from src.tools.synthesis_manager import _find_netlist

    with tempfile.TemporaryDirectory() as run_dir:
        inputs_dir = os.path.join(run_dir, "inputs")
        os.makedirs(inputs_dir, exist_ok=True)
        open(os.path.join(inputs_dir, "top.v"), "w", encoding="utf-8").write("module top(); endmodule\n")

        assert _find_netlist(run_dir, "top") is None


def test_post_synth_compile_excludes_design_rtl(monkeypatch):
    """#51: post_synth compiles testbench + gate netlist + stdcell models and
    EXCLUDES the design RTL the netlist replaces — otherwise the design module is
    declared twice (once by the RTL source, once by the netlist)."""
    with tempfile.TemporaryDirectory() as workspace:
        netlist = os.path.join(workspace, "6_final.v")
        design_rtl = os.path.join(workspace, "top.v")
        tb = os.path.join(workspace, "tb.v")
        stdcell = os.path.join(workspace, "_stdcells", "nangate45", "sim", "dummy.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(netlist, "w", encoding="utf-8").write("module top(); endmodule // gate netlist\n")
        open(design_rtl, "w", encoding="utf-8").write("module top(); endmodule // pre-synth RTL\n")
        open(tb, "w", encoding="utf-8").write("module tb; top u0(); endmodule\n")
        open(stdcell, "w", encoding="utf-8").write("module dummy; endmodule\n")

        captured = {}

        def fake_compile(**kwargs):
            captured["compile_files"] = kwargs["compile_files"]
            return {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"}

        monkeypatch.setattr(rs, "resolve_stdcell_models", lambda ws, platform: ([stdcell], {"files": []}))
        monkeypatch.setattr(rs, "_compile", fake_compile)
        monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[design_rtl, tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            netlist_file=netlist,
            platform="nangate45",
            pass_marker="TEST PASSED",
        )

        assert result["status"] == "test_passed"
        compile_files = captured["compile_files"]
        assert os.path.abspath(netlist) in compile_files        # gate netlist compiled
        assert os.path.abspath(tb) in compile_files             # testbench kept
        assert os.path.abspath(design_rtl) not in compile_files  # design RTL dropped
        assert stdcell in compile_files                         # stdcell models compiled

