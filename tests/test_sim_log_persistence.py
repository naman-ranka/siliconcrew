"""Isolated sim runs persist the full compile+run log (dev#71 / invariant 5).

The run record only ever carried 40-line/4000-char tails, so a failing sim's
evidence was unrecoverable once the process exited. The run directory is the
database: ``sim_runs/sim_NNNN/sim.log`` holds the un-truncated streams.

These tests monkeypatch ``rs._compile`` / ``rs._simulate`` (the pattern in
tests/test_simulation_contract.py) rather than injecting a fake ``_runner`` —
the log write lives inside run_simulation, so replacing it can't exercise it.
"""
import os

from src.tools import run_simulation as rs
from src.tools import sim_manager as sm


COMPILE_STDOUT = "\n".join(f"compile line {i}" for i in range(300))
RUN_STDOUT = "\n".join(f"run line {i}" for i in range(300)) + "\nTEST PASSED\n"


def _patch_toolchain(monkeypatch, compile_rc=0, sim_rc=0):
    monkeypatch.setattr(rs, "_compile", lambda **kw: {
        "returncode": compile_rc,
        "stdout": COMPILE_STDOUT,
        "stderr": "compile stderr detail",
        "command": "iverilog -g2012 -o tb.out -f files.f",
    })
    monkeypatch.setattr(rs, "_simulate", lambda **kw: {
        "returncode": sim_rc,
        "stdout": RUN_STDOUT,
        "stderr": "run stderr detail",
        "command": "vvp tb.out",
    })


def _ws(tmp_path):
    ws = str(tmp_path)
    with open(os.path.join(ws, "tb.v"), "w", encoding="utf-8") as f:
        f.write("module tb; endmodule\n")
    return ws


def test_isolated_run_writes_full_log_and_records_it(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    _patch_toolchain(monkeypatch)

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb")

    assert r["logFile"] == "sim.log"
    log_abs = os.path.join(ws, "sim_runs", r["id"], "sim.log")
    assert os.path.exists(log_abs)

    with open(log_abs, "r", encoding="utf-8") as f:
        log = f.read()

    assert "=== COMPILE ===" in log
    assert "=== RUN ===" in log
    # Both streams, in full — well past the tail caps.
    assert "compile line 0" in log
    assert "run line 0" in log
    assert "compile stderr detail" in log
    assert "run stderr detail" in log
    assert len(log) > 4000
    assert len(log.splitlines()) > 40


def test_run_meta_tails_unchanged(tmp_path, monkeypatch):
    """The tails serve the quick-read path — the log does not change them."""
    ws = _ws(tmp_path)
    _patch_toolchain(monkeypatch)

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb")

    assert len(r["stdoutTail"].splitlines()) <= 40
    assert len(r["stdoutTail"]) <= 4000
    # The head of the stream is exactly what the tail loses and the log keeps.
    assert "run line 0" not in r["stdoutTail"]
    assert "run line 299" in r["stdoutTail"]


def test_compile_failure_persists_its_log(tmp_path, monkeypatch):
    """The failing case is the one that needs the evidence most."""
    ws = _ws(tmp_path)
    _patch_toolchain(monkeypatch, compile_rc=1)

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb")

    assert r["status"] == "failed"
    assert r["logFile"] == "sim.log"
    with open(os.path.join(ws, "sim_runs", r["id"], "sim.log"), "r", encoding="utf-8") as f:
        log = f.read()
    assert "=== COMPILE ===" in log
    assert "compile line 0" in log
    # Nothing ran, so there is no run section to claim.
    assert "=== RUN ===" not in log


def test_early_return_emits_no_log_file_key(tmp_path):
    """run_simulation has early returns that produce no streams — the record
    must not advertise a log that was never written."""
    ws = _ws(tmp_path)

    r = sm.run_sim_isolated(ws, ["tb.v"], "tb", sim_profile="bogus")

    assert "logFile" not in r
    assert not os.path.exists(os.path.join(ws, "sim_runs", r["id"], "sim.log"))


def test_legacy_non_isolated_path_writes_no_log(tmp_path, monkeypatch):
    """No run dir means no honest place to put a log — the legacy path gets none."""
    ws = _ws(tmp_path)
    _patch_toolchain(monkeypatch)

    result = rs.run_simulation(verilog_files=[os.path.join(ws, "tb.v")],
                               top_module="tb", cwd=ws)

    assert result["status"] == "test_passed"
    assert not any(name.endswith(".log") for name in os.listdir(ws))
