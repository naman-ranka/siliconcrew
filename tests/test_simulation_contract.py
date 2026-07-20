import json
import os
import tempfile

from src.tools import run_simulation as rs
from src.tools import sim_manager as sm


def _make_synth_run_with_contract(ws, run_id="synth_0001", platform="sky130hd"):
    """Workspace with an RTL source AND a synth run whose sim_contract points at
    the GATE netlist (workspace-relative). Returns (tb_path, gate_abs, gate_rel)."""
    # RTL source with the same top — the netlist-vs-RTL trap.
    with open(os.path.join(ws, "top.v"), "w", encoding="utf-8") as f:
        f.write("module top(input a, output b); assign b = a; endmodule\n")
    tb = os.path.join(ws, "tb.v")
    with open(tb, "w", encoding="utf-8") as f:
        f.write("module tb; top u0(); endmodule\n")

    run_dir = os.path.join(ws, "synth_runs", run_id)
    results = os.path.join(run_dir, "orfs_results", platform, "top", "base")
    os.makedirs(results, exist_ok=True)
    gate_abs = os.path.join(results, "6_final.v")
    with open(gate_abs, "w", encoding="utf-8") as f:
        f.write("module top(); endmodule\n")
    gate_rel = os.path.relpath(gate_abs, ws).replace(os.sep, "/")
    meta = {
        "run_id": run_id, "platform": platform, "top_module": "top",
        "netlist_path": gate_abs,
        "sim_contract": {
            "schema_version": 1, "mode": "post_synth", "platform": platform,
            "top": "top", "netlist": gate_rel, "stdcell_platform": platform,
            "stdcell_manifest_version": "v1",
        },
    }
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return tb, gate_abs, gate_rel


def test_post_synth_resolves_gate_netlist_from_contract_and_echoes(monkeypatch):
    """Core #52 regression: post_synth resolves the real gate netlist from the
    run record (NOT the RTL), and the result echoes what was resolved."""
    with tempfile.TemporaryDirectory() as ws:
        tb, gate_abs, gate_rel = _make_synth_run_with_contract(ws)
        stdcell = os.path.join(ws, "_stdcells", "sky130hd", "sim", "dummy.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(stdcell, "w").write("module dummy; endmodule")

        monkeypatch.setattr(rs, "resolve_stdcell_models",
                            lambda workspace_arg, platform_arg: ([stdcell], {"files": []}))
        captured = {}

        def fake_compile(**kwargs):
            captured["compile_files"] = kwargs["compile_files"]
            return {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"}

        monkeypatch.setattr(rs, "_compile", fake_compile)
        monkeypatch.setattr(rs, "_simulate",
                            lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[tb], top_module="tb", cwd=ws, workspace=ws,
            mode="post_synth", run_id="synth_0001",
        )

        assert result["status"] == "test_passed"
        assert result["outcome"] == "test_passed"
        # The GATE netlist was compiled, not the RTL top.v (normpath: the netlist
        # arrives workspace-relative POSIX from the contract).
        _compiled = [os.path.normpath(p) for p in captured["compile_files"]]
        assert os.path.normpath(gate_abs) in _compiled
        assert os.path.normpath(os.path.join(ws, "top.v")) not in _compiled
        # Honest echo of what was resolved.
        assert result["resolved_run_id"] == "synth_0001"
        assert result["resolved_netlist"] == gate_rel
        assert result["stdcell_source"] == "sky130hd"


def test_post_synth_excludes_design_rtl_from_compile_set(monkeypatch):
    """#52 double-declaration guard: given the REAL manifest simulate set
    [design RTL, testbench], post_synth compiles the testbench + gate netlist +
    stdcells only — never the design RTL the netlist replaces (which would
    re-declare the design module, 'already declared')."""
    from collections import Counter

    with tempfile.TemporaryDirectory() as ws:
        tb, gate_abs, gate_rel = _make_synth_run_with_contract(ws)
        rtl = os.path.join(ws, "top.v")  # the design source the netlist replaces
        stdcell = os.path.join(ws, "_stdcells", "sky130hd", "sim", "dummy.v")
        os.makedirs(os.path.dirname(stdcell), exist_ok=True)
        open(stdcell, "w").write("module dummy; endmodule")

        monkeypatch.setattr(rs, "resolve_stdcell_models",
                            lambda workspace_arg, platform_arg: ([stdcell], {"files": []}))
        captured = {}

        def fake_compile(**kwargs):
            captured["compile_files"] = kwargs["compile_files"]
            return {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"}

        monkeypatch.setattr(rs, "_compile", fake_compile)
        monkeypatch.setattr(rs, "_simulate",
                            lambda **kwargs: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[rtl, tb], top_module="tb", cwd=ws, workspace=ws,
            mode="post_synth", run_id="synth_0001",
        )

        assert result["status"] == "test_passed"
        # normpath every path: the gate netlist arrives workspace-relative POSIX
        # from the contract, so on Windows it's mixed-separator vs native inputs.
        compiled = [os.path.normpath(p) for p in captured["compile_files"]]
        # (a) The design RTL source is NOT compiled; the gate netlist + testbench are.
        assert os.path.normpath(rtl) not in compiled
        assert os.path.normpath(gate_abs) in compiled
        assert os.path.normpath(tb) in compiled
        # (b) No double-declaration: the design module 'top' is declared by exactly
        # one compiled source (the gate netlist), not also by the RTL.
        mod_counts: Counter = Counter()
        for f in compiled:
            for mod in rs._collect_defined_modules([f]):
                mod_counts[mod] += 1
        assert mod_counts["top"] == 1


def test_post_synth_missing_cache_yields_semantic_recoverable_outcome(monkeypatch):
    """A missing stdcell cache is a typed, recoverable outcome that names a
    native platform action — not a raw traceback."""
    with tempfile.TemporaryDirectory() as ws:
        tb, gate_abs, gate_rel = _make_synth_run_with_contract(ws)

        monkeypatch.setattr(
            rs, "resolve_stdcell_models",
            lambda workspace_arg, platform_arg: (_ for _ in ()).throw(
                FileNotFoundError("Standard-cell cache missing for platform 'sky130hd'.")
            ),
        )

        result = rs.run_simulation(
            verilog_files=[tb], top_module="tb", cwd=ws, workspace=ws,
            mode="post_synth", run_id="synth_0001",
        )

        assert result["status"] == "compile_failed"
        assert result["outcome"] == "stdcell_cache_missing"
        assert result["recovery"]["kind"] == "infra"
        assert "action" not in result["recovery"]
        # Still echoes what it did resolve (run + netlist) before the cache miss.
        assert result["resolved_run_id"] == "synth_0001"
        assert result["resolved_netlist"] == gate_rel


def test_post_synth_unknown_run_is_typed_outcome():
    with tempfile.TemporaryDirectory() as ws:
        open(os.path.join(ws, "tb.v"), "w").write("module tb; endmodule")
        result = rs.run_simulation(
            verilog_files=[os.path.join(ws, "tb.v")], top_module="tb",
            cwd=ws, workspace=ws, mode="post_synth", run_id="synth_4242",
        )
        assert result["status"] == "compile_failed"
        assert result["outcome"] == "run_not_found"
        assert result["recovery"] is None


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
        # The hint points at the install root (stdcell_root), and is honest that
        # a hosted/self-host deploy bakes the models so this should never happen.
        from src.tools.stdcells import stdcell_root
        assert stdcell_root() in result["stderr_tail"]
        assert "baked into the backend image" in result["stderr_tail"]


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


def test_post_synth_stdcells_resolve_when_agent_repoints_rtl_workspace(monkeypatch):
    """Issue #59 regression — the AGENT/SUBPROCESS path, which four prior fixes
    never covered because every one verified through /mcp (the leg that worked).

    An agent turn spawns the MCP server subprocess with RTL_WORKSPACE re-pointed
    to the per-session scratch *base* — codex_engine.py does exactly
    ``env["RTL_WORKSPACE"] = _workspace_base(turn.workspace, turn.session_id)``,
    which strips the session id ("/tmp/siliconcrew-scratch/pwm-generator" ->
    "/tmp/siliconcrew-scratch"). That base holds session workspaces, NOT the PDK.
    Standard-cell resolution must not follow it: the models are install-global,
    resolved from the code root every caller shares by construction.

    This drives the real ``run_simulation`` post_synth path and captures the
    workspace it hands to ``resolve_stdcell_models``. Tree-agnostic on purpose so
    the SAME assertion runs pre- and post-fix: PRE-FIX that workspace was exactly
    the re-pointed RTL_WORKSPACE and the assertion FAILS (the live symptom was
    ``outcome: stdcell_cache_missing`` naming the scratch root); post-fix it is
    the install root and the assertion passes.
    """
    from src.agents.codex.codex_engine import _workspace_base

    with tempfile.TemporaryDirectory() as ws:
        tb, gate_abs, gate_rel = _make_synth_run_with_contract(ws)

        # Reproduce the agent turn's env verbatim (codex_engine.py:650, :687).
        session_workspace = os.path.join("/tmp", "siliconcrew-scratch", "pwm-generator")
        scratch_base = _workspace_base(session_workspace, "pwm-generator")
        assert scratch_base == os.path.join("/tmp", "siliconcrew-scratch")
        monkeypatch.setenv("RTL_WORKSPACE", scratch_base)

        captured = {}

        def fake_resolve(workspace_arg, platform_arg):
            captured["workspace"] = workspace_arg
            model = os.path.join(ws, "_stdcells", "sky130hd", "sim", "dummy.v")
            os.makedirs(os.path.dirname(model), exist_ok=True)
            open(model, "w").write("module dummy; endmodule")
            return ([model], {"files": []})

        monkeypatch.setattr(rs, "resolve_stdcell_models", fake_resolve)
        monkeypatch.setattr(rs, "_compile", lambda **k: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"})
        monkeypatch.setattr(rs, "_simulate", lambda **k: {"returncode": 0, "stdout": "TEST PASSED\n", "stderr": "", "command": "vvp"})

        result = rs.run_simulation(
            verilog_files=[tb], top_module="tb", cwd=ws, workspace=ws,
            mode="post_synth", run_id="synth_0001",
        )

        # The defect: post-synth stdcell resolution followed the re-pointed
        # RTL_WORKSPACE (the scratch base), so the subprocess looked for
        # <scratch_base>/_stdcells and never found the baked PDK.
        assert captured["workspace"] != os.path.abspath(scratch_base)
        # It must resolve from the install-global PDK root instead.
        from src.tools.stdcells import stdcell_root
        assert captured["workspace"] == stdcell_root()
        assert result["status"] == "test_passed"
        assert result["outcome"] == "test_passed"

