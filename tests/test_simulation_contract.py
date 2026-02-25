import os
import tempfile

from src.tools import run_simulation as rs


def test_simulation_requires_explicit_pass_marker(monkeypatch):
    monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
    monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "PASS generic\n", "stderr": "", "command": "vvp"})

    result = rs.run_simulation(verilog_files=[], top_module="tb", mode="rtl", pass_marker="TEST PASSED")
    assert result["status"] == "test_failed"
    assert result["pass_marker_found"] is False


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
