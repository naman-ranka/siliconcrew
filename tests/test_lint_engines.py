"""Lint engine abstraction: one diagnostic contract, pluggable engines.

Parsing lives in src/tools/run_linter.py (moved out of the REST layer so the
agent tool, REST, and any future caller share ONE structured contract).
"""
import os

import pytest

from src.tools import run_linter as rl

VERILATOR_OUT = """%Warning-WIDTH: alu.v:12:9: Operator ASSIGN expects 8 bits on the Assign RHS, but Assign RHS's CONST '4'h3' generates 4 bits.
                                             : ... In instance alu
%Warning-LATCH: ctrl.v:33:1: Latch inferred for signal 'ctrl.state_n'
%Error: top.v:3:10: Cannot find file containing module: 'missing_mod'
%Error-PINMISSING: alu.v:40:5: Cell has missing pin: 'rst'
"""

IVERILOG_ERR = """alu.v:7: syntax error
alu.v:7: error: malformed statement
ctrl.v:12: warning: implicit definition of wire 'foo'.
"""


def test_parse_verilator_diagnostics():
    diags = rl.parse_verilator_diagnostics(VERILATOR_OUT)
    assert len(diags) == 4
    w = diags[0]
    assert (w["file"], w["line"], w["severity"], w["code"]) == ("alu.v", 12, "warning", "WIDTH")
    assert diags[1]["code"] == "LATCH"
    assert diags[2]["severity"] == "error" and diags[2]["code"] is None
    assert diags[3]["code"] == "PINMISSING"


def test_parse_iverilog_diagnostics_matches_legacy_contract():
    diags = rl.parse_iverilog_diagnostics(IVERILOG_ERR)
    sevs = [(d["file"], d["line"], d["severity"]) for d in diags]
    assert ("alu.v", 7, "error") in sevs
    assert ("ctrl.v", 12, "warning") in sevs
    assert all(d["code"] is None for d in diags)


def test_norm_file_relativizes_into_workspace(tmp_path):
    ws = str(tmp_path)
    absolute = os.path.join(ws, "rtl", "alu.v")
    diags = rl.parse_verilator_diagnostics(f"%Warning-WIDTH: {absolute}:5: msg", cwd=ws)
    assert diags[0]["file"] == "rtl/alu.v"


def test_resolve_engine_auto_prefers_verilator(monkeypatch):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert rl.resolve_engine("auto") == {"engine": "verilator"}


def test_resolve_engine_auto_falls_back_to_iverilog(monkeypatch):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    assert rl.resolve_engine("auto") == {"engine": "iverilog"}


def test_resolve_engine_explicit_missing_is_honest(monkeypatch):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None)
    out = rl.resolve_engine("verilator")
    assert "not installed" in out["error"]
    out = rl.resolve_engine("bogus")
    assert "Unknown lint engine" in out["error"]


def test_run_linter_unavailable_engine_returns_structured_error(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None)
    result = rl.run_linter(["a.v"], cwd=str(tmp_path), engine="verilator")
    assert result["success"] is False
    assert result["engine"] is None
    assert result["diagnostics"][0]["code"] == "ENGINE"


def test_run_linter_verilator_end_to_end_with_fake_binary(monkeypatch, tmp_path):
    """Engine selection + command construction + parsing, without verilator
    installed: stub the subprocess layer."""
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    def fake_run(cmd, cwd, timeout):
        captured["cmd"] = cmd
        return {"returncode": 0, "stdout": "", "stderr": VERILATOR_OUT, "command": " ".join(cmd)}

    monkeypatch.setattr(rl, "_run", fake_run)
    result = rl.run_linter([str(tmp_path / "alu.v")], cwd=str(tmp_path), engine="verilator")
    assert captured["cmd"][:7] == [
        "verilator", "--lint-only", "--timing", "-Wall", "-Wno-fatal",
        "-Wno-EOFNEWLINE", "-Wno-DECLFILENAME",
    ]
    assert result["engine"] == "verilator"
    # Errors present in the parsed diagnostics → success False even with rc 0.
    assert result["success"] is False
    assert any(d["code"] == "LATCH" for d in result["diagnostics"])


def test_run_linter_iverilog_success_keeps_legacy_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")

    def fake_run(cmd, cwd, timeout):
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cmd)}

    monkeypatch.setattr(rl, "_run", fake_run)
    result = rl.run_linter(["a.v"], cwd=str(tmp_path), engine="auto")
    assert result["success"] is True
    assert result["engine"] == "iverilog"
    for key in ("stdout", "stderr", "command"):  # legacy contract preserved
        assert key in result
