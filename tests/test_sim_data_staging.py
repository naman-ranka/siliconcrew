"""Runtime data staging for isolated sims + the false-PASS fence (D3, sc#65).

vvp runs with cwd=<run dir>, so a testbench's `$readmemb("weights.mem", …)` had
nothing to open. Worse, that failure prints to STDOUT and vvp exits 0 — a TB
that doesn't self-check reads all-X memory, prints its pass marker, and the run
was recorded as PASSED on garbage.
"""
import json
import os
import shutil

import pytest

from src.tools import manifest as manifest_mod
from src.tools import sim_manager as sm
from src.tools.run_simulation import run_simulation


TB_READMEM = """
module mem_tb;
    reg [7:0] mem [0:3];
    integer i;
    initial begin
        $readmemb("weights.mem", mem);
        if (mem[0] === 8'bxxxxxxxx) begin
            $display("LOADED NOTHING");
        end
        $display("TEST PASSED");
        $finish;
    end
endmodule
"""

WEIGHTS = "00000001\n00000010\n00000011\n00000100\n"


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _fake_runner(**expectations):
    """A run_simulation stand-in that records the cwd it was given."""
    def runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
               platform, sim_profile, pass_marker, timeout, log_path=None):
        return {"status": "test_passed", "pass_marker_found": True, "stdout_tail": "",
                "stderr_tail": "", "log_truncated": False}
    return runner


def test_data_file_is_staged_at_both_placements(tmp_path):
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "data/weights.mem", WEIGHTS)

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    run_dir = os.path.join(ws, "sim_runs", run["id"])

    assert os.path.isfile(os.path.join(run_dir, "data", "weights.mem"))
    assert os.path.isfile(os.path.join(run_dir, "weights.mem"))
    assert run["stagedDataFiles"] == [
        {"source": "data/weights.mem", "stagedAs": ["data/weights.mem", "weights.mem"]}
    ]
    # The run record on disk carries the same evidence.
    with open(os.path.join(run_dir, "run_meta.json"), encoding="utf-8") as f:
        assert json.load(f)["stagedDataFiles"] == run["stagedDataFiles"]


def test_non_data_files_are_not_staged(tmp_path):
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "README.md", "# notes\n")
    _write(ws, "notes.pdf", "x")

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    run_dir = os.path.join(ws, "sim_runs", run["id"])

    assert run["stagedDataFiles"] == []
    assert not os.path.exists(os.path.join(run_dir, "README.md"))
    assert not os.path.exists(os.path.join(run_dir, "notes.pdf"))


def test_ignored_data_file_is_not_staged(tmp_path):
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "vendor/golden.mem", WEIGHTS)
    _write(ws, "weights.mem", WEIGHTS)
    manifest_mod.read_manifest(ws, session_id="s1")
    manifest_mod.write_manifest(ws, {"ignore": ["vendor/**"]})

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    run_dir = os.path.join(ws, "sim_runs", run["id"])

    assert [s["source"] for s in run["stagedDataFiles"]] == ["weights.mem"]
    assert not os.path.exists(os.path.join(run_dir, "vendor", "golden.mem"))


def test_ambiguous_basename_stages_relative_only(tmp_path):
    """Two files named init.mem can't both be the run-dir root init.mem."""
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "cpu/init.mem", WEIGHTS)
    _write(ws, "gpu/init.mem", WEIGHTS)

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    run_dir = os.path.join(ws, "sim_runs", run["id"])

    assert run["stagedDataFiles"] == [
        {"source": "cpu/init.mem", "stagedAs": ["cpu/init.mem"]},
        {"source": "gpu/init.mem", "stagedAs": ["gpu/init.mem"]},
    ]
    assert not os.path.exists(os.path.join(run_dir, "init.mem"))


def test_prior_run_artifacts_are_never_staged(tmp_path):
    """sim_runs/ is pruned by the scan — one run's output can't leak into another."""
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "weights.mem", WEIGHTS)
    first = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    _write(ws, os.path.join("sim_runs", first["id"], "leftover.dat"), "stale\n")

    second = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb", _runner=_fake_runner())
    assert [s["source"] for s in second["stagedDataFiles"]] == ["weights.mem"]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_readmem_tb_passes_from_the_run_dir(tmp_path):
    """The real toolchain, end to end: fails pre-fix with can't-open."""
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)
    _write(ws, "weights.mem", WEIGHTS)

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb")
    assert run["status"] == "passed", run
    assert "LOADED NOTHING" not in (run["stdoutTail"] or "")


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_missing_data_file_cannot_record_a_pass(tmp_path):
    """The false-PASS repro: $readmem fails on stdout, vvp exits 0, TB prints
    its pass marker anyway. Pre-fix this recorded test_passed."""
    ws = str(tmp_path)
    _write(ws, "mem_tb.v", TB_READMEM)  # no weights.mem anywhere

    result = run_simulation(
        verilog_files=[os.path.join(ws, "mem_tb.v")], top_module="mem_tb", cwd=ws,
    )
    assert result["sim_returncode"] == 0          # vvp was happy
    assert result["pass_marker_found"] is True    # the marker really is there
    assert result["status"] == "sim_failed"       # ...and the run still is not a pass
    assert result["failure_type"] == "data_file_missing"
    assert "Unable to open" in (result["first_failure_line"] or "")

    run = sm.run_sim_isolated(ws, ["mem_tb.v"], "mem_tb")
    assert run["status"] == "failed"
