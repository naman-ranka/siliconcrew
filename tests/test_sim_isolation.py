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
