"""Sim-run isolation: each sim gets its own sim_runs/sim_NNNN/ + VCD + record.

These tests inject a fake runner so they do not require iverilog — the contract
being verified is the isolation/indexing/provenance scaffolding, not the EDA
toolchain itself.
"""
import os

from src.tools import sim_manager as sm


def _fake_runner_factory(status="test_passed", write_vcd=True, marker="dump.vcd"):
    """Return a run_simulation stand-in that writes a VCD into cwd."""

    def runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
               platform, sim_profile, pass_marker, timeout):
        if write_vcd:
            with open(os.path.join(cwd, marker), "w", encoding="utf-8") as f:
                f.write("$date fake $end\n")
        # also drop the compiled artifact like iverilog would
        with open(os.path.join(cwd, f"{top_module}.out"), "w") as f:
            f.write("bin")
        return {
            "status": status,
            "pass_marker_found": status == "test_passed",
            "compile_command": "iverilog -g2012 -o tb.out -f files.f",
            "sim_command": "vvp tb.out",
            "stdout_tail": "TEST PASSED" if status == "test_passed" else "t=240ns ERROR mismatch",
            "stderr_tail": "",
            "log_truncated": False,
            "failure_type": None if status == "test_passed" else "test_failed",
            "first_failure_line": None if status == "test_passed" else "t=240ns ERROR mismatch",
        }

    return runner


def test_each_sim_run_isolated_with_own_dir_and_vcd(tmp_path):
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()

    r1 = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory())
    r2 = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory())

    assert r1["id"] == "sim_0001"
    assert r2["id"] == "sim_0002"
    # Distinct directories — no collision.
    assert r1["vcdPath"] == os.path.join("sim_runs", "sim_0001", "dump.vcd")
    assert r2["vcdPath"] == os.path.join("sim_runs", "sim_0002", "dump.vcd")
    assert os.path.exists(os.path.join(ws, r1["vcdPath"]))
    assert os.path.exists(os.path.join(ws, r2["vcdPath"]))
    # Per-run record persisted.
    assert os.path.exists(os.path.join(ws, "sim_runs", "sim_0001", "run_meta.json"))


def test_status_and_failure_mapping(tmp_path):
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()

    ok = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory("test_passed"))
    assert ok["status"] == "passed"
    assert ok["passMarkerFound"] is True
    assert ok["failure"] is None

    bad = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory("test_failed"))
    assert bad["status"] == "failed"
    assert bad["failure"]["type"] == "test_failed"
    assert bad["failure"]["timeNs"] == 240  # parsed from "t=240ns"


def test_provenance_and_commands_stamped(tmp_path):
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()
    r = sm.run_sim_isolated(ws, ["tb.v"], "tb", platform="sky130hd", _runner=_fake_runner_factory())
    assert "provenance" in r and "repoCommit" in r["provenance"]
    assert r["provenance"]["pdk"] == "sky130hd"
    assert r["compileCommand"].startswith("iverilog")
    assert r["simCommand"].startswith("vvp")


def test_list_and_get_and_pin(tmp_path):
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()
    sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory())
    sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner_factory("test_failed"))

    runs = sm.list_sim_runs(ws)
    assert [r["id"] for r in runs] == ["sim_0002", "sim_0001"]  # newest first
    assert all(r["kind"] == "sim" for r in runs)

    got = sm.get_sim_run(ws, "sim_0001")
    assert got["id"] == "sim_0001"

    pinned = sm.set_sim_run_pinned(ws, "sim_0001", True)
    assert pinned["pinned"] is True
    assert any(r["id"] == "sim_0001" and r["pinned"] for r in sm.list_sim_runs(ws))


def test_no_runs_dir_returns_empty(tmp_path):
    assert sm.list_sim_runs(str(tmp_path)) == []


def _make_synth_run(ws, run_id="synth_0001", platform="sky130hd", netlist_name="6_final.v"):
    """Create a workspace synth_runs/<run_id>/ with run_meta.json + netlist."""
    run_dir = os.path.join(ws, "synth_runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    netlist_abs = os.path.join(run_dir, netlist_name)
    with open(netlist_abs, "w", encoding="utf-8") as f:
        f.write("module top(); endmodule\n")
    import json

    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"netlist_path": netlist_abs, "platform": platform}, f)
    return netlist_abs


def test_post_synth_resolves_run_against_workspace_not_sim_dir(tmp_path):
    """Regression: run_sim_isolated must resolve the synth run against the
    workspace root, not the isolated sim exec cwd.

    Before the fix, run_sim_isolated forwarded ``run_id`` and no netlist to
    run_simulation, whose ``get_run_dir(cwd, run_id)`` searched
    ``<sim_run_dir>/synth_runs/<run_id>`` — which never exists — and failed
    with "Unknown run_id". The netlist actually lives under
    ``<workspace>/synth_runs/<run_id>``.
    """
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()
    netlist_abs = _make_synth_run(ws, run_id="synth_0001")

    captured = {}

    def spy_runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
                   platform, sim_profile, pass_marker, timeout):
        captured.update(
            run_id=run_id, netlist_file=netlist_file, platform=platform, cwd=cwd
        )
        with open(os.path.join(cwd, f"{top_module}.out"), "w") as f:
            f.write("bin")
        return {"status": "test_passed", "pass_marker_found": True,
                "compile_command": "iverilog", "sim_command": "vvp",
                "stdout_tail": "", "stderr_tail": "", "log_truncated": False,
                "failure_type": None, "first_failure_line": None}

    sm.run_sim_isolated(
        ws, ["tb.v"], "tb", mode="post_synth", run_id="synth_0001",
        _runner=spy_runner,
    )

    # Netlist resolved to the WORKSPACE synth run, not under the sim dir.
    assert os.path.normpath(captured["netlist_file"]) == os.path.normpath(netlist_abs)
    assert os.path.isabs(captured["netlist_file"])
    assert os.path.exists(captured["netlist_file"])
    assert "sim_runs" not in captured["netlist_file"]
    # Platform pulled from the synth run_meta.
    assert captured["platform"] == "sky130hd"
    # run_id already resolved upstream — don't let run_simulation re-resolve it
    # under the (sim) exec cwd.
    assert captured["run_id"] is None
    # Execution cwd is still the isolated sim dir (for iverilog/vvp).
    assert captured["cwd"].endswith(os.path.join("sim_runs", "sim_0001"))


def _make_synth_run_with_contract(ws, run_id="synth_0001", platform="sky130hd"):
    """Synth run whose sim_contract points at the GATE netlist (ws-relative)."""
    run_dir = os.path.join(ws, "synth_runs", run_id)
    results = os.path.join(run_dir, "orfs_results", platform, "top", "base")
    os.makedirs(results, exist_ok=True)
    gate_abs = os.path.join(results, "6_final.v")
    with open(gate_abs, "w", encoding="utf-8") as f:
        f.write("module top(); endmodule\n")
    gate_rel = os.path.relpath(gate_abs, ws).replace(os.sep, "/")
    import json

    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "run_id": run_id, "platform": platform, "top_module": "top",
            "netlist_path": gate_abs,
            "sim_contract": {
                "schema_version": 1, "mode": "post_synth", "platform": platform,
                "top": "top", "netlist": gate_rel,
                "stdcell_manifest_version": "v1",
            },
        }, f)
    return gate_abs, gate_rel


def test_isolated_post_synth_echoes_resolved_contract(tmp_path):
    """The isolated SimRun record echoes what post-synth resolution picked from
    the contract (run id, gate netlist, stdcell source) — no hidden magic."""
    ws = str(tmp_path)
    # An RTL top.v exists too; the spy must receive the GATE netlist.
    open(os.path.join(ws, "top.v"), "w").write("module top(); endmodule")
    open(os.path.join(ws, "tb.v"), "w").close()
    gate_abs, gate_rel = _make_synth_run_with_contract(ws)

    captured = {}

    def spy_runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
                   platform, sim_profile, pass_marker, timeout):
        captured.update(netlist_file=netlist_file, platform=platform, run_id=run_id)
        with open(os.path.join(cwd, f"{top_module}.out"), "w") as f:
            f.write("bin")
        return {"status": "test_passed", "pass_marker_found": True,
                "outcome": "test_passed", "recovery": None,
                "compile_command": "iverilog", "sim_command": "vvp",
                "stdout_tail": "", "stderr_tail": "", "log_truncated": False,
                "failure_type": None, "first_failure_line": None}

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb", mode="post_synth",
                            run_id="synth_0001", _runner=spy_runner)

    assert r["status"] == "passed"
    # Gate netlist resolved from the contract, not the RTL. normpath both sides:
    # the contract path is workspace-relative POSIX, so on Windows the resolved
    # absolute is mixed-separator vs a native gate_abs.
    assert os.path.normpath(captured["netlist_file"]) == os.path.normpath(gate_abs)
    assert "top.v" not in os.path.relpath(captured["netlist_file"], ws)
    assert captured["run_id"] is None  # resolved upstream; not re-resolved
    # Echoes on the persisted record.
    assert r["resolvedRunId"] == "synth_0001"
    assert r["resolvedNetlist"] == gate_rel
    assert r["stdcellSource"] == "sky130hd"
    assert r["outcome"] == "test_passed"
    persisted = sm.get_sim_run(ws, r["id"])
    assert persisted["resolvedNetlist"] == gate_rel


def test_isolated_post_synth_unknown_run_is_typed_failure(tmp_path):
    """An unknown run yields a typed, persisted SimRun card — not an exception."""
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb", mode="post_synth",
                            run_id="synth_9999",
                            _runner=_fake_runner_factory())

    assert r["status"] == "failed"
    assert r["outcome"] == "run_not_found"
    assert r["failure"]["type"] == "run_not_found"
    # Persisted + indexed so the IDE/agent can read it back.
    assert sm.get_sim_run(ws, r["id"]) is not None


def test_isolated_post_synth_missing_cache_recovery_propagates(tmp_path):
    """A stdcell_cache_missing outcome from the runner surfaces on the SimRun
    record with its native recovery action."""
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()
    _make_synth_run_with_contract(ws)

    def cache_miss_runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
                          platform, sim_profile, pass_marker, timeout):
        with open(os.path.join(cwd, f"{top_module}.out"), "w") as f:
            f.write("bin")
        return {"status": "compile_failed", "pass_marker_found": False,
                "outcome": "stdcell_cache_missing",
                "recovery": {"kind": "infra", "label": "x", "detail": "y"},
                "compile_command": "iverilog", "sim_command": None,
                "stdout_tail": "", "stderr_tail": "cache missing", "log_truncated": False,
                "failure_type": "compile", "first_failure_line": "cache missing"}

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb", mode="post_synth",
                            run_id="synth_0001", _runner=cache_miss_runner)

    assert r["status"] == "failed"
    assert r["outcome"] == "stdcell_cache_missing"
    assert r["recovery"]["kind"] == "infra"


def test_post_synth_gets_past_run_resolution_with_real_runner(tmp_path):
    """End-to-end: with the real run_simulation, post_synth via the isolated
    path resolves a workspace synth run and proceeds PAST run resolution
    (it may still fail later at stdcell/compile, but never with the
    unresolved-run_id / missing-netlist errors)."""
    ws = str(tmp_path)
    open(os.path.join(ws, "tb.v"), "w").close()
    _make_synth_run(ws, run_id="synth_0001")

    # Default _runner is the real run_simulation.
    r = sm.run_sim_isolated(
        ws, ["tb.v"], "tb", mode="post_synth", run_id="synth_0001",
    )

    blob = f"{r.get('stderrTail', '')}\n{r.get('stdoutTail', '')}"
    assert "Unknown run_id" not in blob
    assert "no latest run available" not in blob
    assert "requires a valid synthesized netlist" not in blob
