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


def test_post_synth_auto_bootstraps_stdcells(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        os.makedirs(run_dir, exist_ok=True)
        netlist = os.path.join(run_dir, "netlist.v")
        tb = os.path.join(workspace, "tb.v")
        open(netlist, "w", encoding="utf-8").write("module top; endmodule")
        open(tb, "w", encoding="utf-8").write("module tb; top u0(); endmodule")

        monkeypatch.setattr(rs, "get_run_dir", lambda cwd, run_id: run_dir)
        monkeypatch.delenv("NO_AUTO_BOOTSTRAP", raising=False)

        state = {"resolve_calls": 0, "boot_calls": 0}

        def fake_resolve(workspace_arg, platform_arg):
            state["resolve_calls"] += 1
            if state["resolve_calls"] == 1:
                raise FileNotFoundError("Standard-cell cache missing for platform 'asap7'.")
            stdcell = os.path.join(workspace, "_stdcells", "asap7", "sim", "dummy.v")
            os.makedirs(os.path.dirname(stdcell), exist_ok=True)
            open(stdcell, "w", encoding="utf-8").write("module dummy; endmodule")
            return [stdcell], {"files": [{"name": "dummy.v"}]}

        def fake_bootstrap(*, workspace, platform):
            state["boot_calls"] += 1
            return {"platform": platform, "file_count": 1}

        monkeypatch.setattr(rs, "resolve_stdcell_models", fake_resolve)
        monkeypatch.setattr(rs, "bootstrap_stdcells", fake_bootstrap)
        monkeypatch.setattr(rs, "_compile", lambda **kwargs: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
        monkeypatch.setattr(rs, "_simulate", lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[tb],
            top_module="tb",
            cwd=workspace,
            mode="post_synth",
            run_id="synth_0001",
            netlist_file=netlist,
            platform="asap7",
        )

        assert result["status"] == "test_passed"
        assert result["stdcell_bootstrap_attempted"] is True
        assert state["boot_calls"] == 1


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
