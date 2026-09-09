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
    assert captured["cmd"][:8] == [
        "verilator", "--lint-only", "--timing", "-Wall", "-Wno-fatal",
        "-Wno-EOFNEWLINE", "-Wno-DECLFILENAME", f"+libext+{rl._NO_LIBRARY_EXT}",
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


# --- file-scoped lint (adversarial-review F2) ---------------------------------
#
# "Lint this file" on a hierarchical design compiles ONE file: every module it
# instantiates is missing, which both engines report as an error. That is a
# true statement about the compile and a FALSE verdict about the file. With
# scope_modules = {modules the dropped manifest files define} exactly those
# errors become one honest note; everything else — including an unresolved
# module NO dropped file defines — still fails. No binaries here — this is the
# command-construction / diagnostic-filter layer.

IVERILOG_MISSING_MODULE = """tb.v:5: error: Unknown module type: alu
2 error(s) during elaboration.
*** These modules were missing:
        alu referenced 1 times.
***
"""

IVERILOG_MISSING_PLUS_SYNTAX = """tb.v:3: syntax error
tb.v:3: error: malformed statement
tb.v:5: error: Unknown module type: alu
"""

VERILATOR_MISSING_MODULE = "%Error: top.v:3:10: Cannot find file containing module: 'missing_mod'\n"


def _iverilog(monkeypatch, stderr, returncode=1):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout: {"returncode": returncode, "stdout": "", "stderr": stderr, "command": " ".join(cmd)},
    )


def test_split_unresolved_module_diagnostics_names_each_engine_signature():
    diags = (
        rl.parse_iverilog_diagnostics(IVERILOG_MISSING_MODULE)
        + rl.parse_verilator_diagnostics(VERILATOR_MISSING_MODULE)
    )
    kept, missing = rl.split_unresolved_module_diagnostics(diags)
    assert missing == ["alu", "missing_mod"]
    assert all("Unknown module type" not in (d["message"] or "") for d in kept)


def test_file_scoped_lint_of_a_file_missing_its_submodules_passes_with_a_note(monkeypatch, tmp_path):
    _iverilog(monkeypatch, IVERILOG_MISSING_MODULE)
    result = rl.run_linter(["tb.v"], cwd=str(tmp_path), engine="iverilog", scope_modules={"alu"})
    assert result["success"] is True  # the FILE is fine; its deps were not compiled
    assert not [d for d in result["diagnostics"] if d["severity"] == "error"]
    assert len(result["notes"]) == 1
    assert "alu" in result["notes"][0] and "not in the linted file set" in result["notes"][0]


def test_file_scoped_lint_still_fails_on_a_real_syntax_error(monkeypatch, tmp_path):
    _iverilog(monkeypatch, IVERILOG_MISSING_PLUS_SYNTAX)
    result = rl.run_linter(["tb.v"], cwd=str(tmp_path), engine="iverilog", scope_modules={"alu"})
    assert result["success"] is False
    messages = [d["message"] for d in result["diagnostics"]]
    assert any("malformed statement" in m for m in messages)
    assert all("Unknown module type" not in m for m in messages)
    assert result["notes"]  # the scope is still narrated honestly


def test_file_scoped_lint_of_a_clean_verilator_run_adds_no_note(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout: {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cmd)},
    )
    result = rl.run_linter(["a.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is True and result["notes"] == []


def test_file_scoped_verilator_missing_module_is_a_note_too(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout: {"returncode": 1, "stdout": "", "stderr": VERILATOR_MISSING_MODULE, "command": " ".join(cmd)},
    )
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"missing_mod"})
    assert result["success"] is True
    assert "missing_mod" in result["notes"][0]


def test_whole_design_lint_keeps_unresolved_module_errors(monkeypatch, tmp_path):
    """The default (manifest-resolved set) is unchanged: a module missing from
    the WHOLE design is a real error, not a scoping artifact."""
    _iverilog(monkeypatch, IVERILOG_MISSING_MODULE)
    result = rl.run_linter(["tb.v"], cwd=str(tmp_path), engine="iverilog")
    assert result["success"] is False
    assert any("Unknown module type" in d["message"] for d in result["diagnostics"])
    assert result["notes"] == []


# --- adversarial-review P2-1: a note may only state what the manifest knows ---

def test_file_scoped_lint_keeps_a_module_no_dropped_file_defines(monkeypatch, tmp_path):
    """``countr`` (typo) is unresolved in EVERY file set; the dropped file
    defines ``counter``. Pre-fix every unresolved name became a note and the
    file PASSED — a false pass by construction."""
    _iverilog(monkeypatch, "top.v:3: error: Unknown module type: countr\n")
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="iverilog", scope_modules={"counter"})
    assert result["success"] is False
    assert any("Unknown module type: countr" in d["message"] for d in result["diagnostics"])
    assert result["notes"] == []


def test_file_scoped_lint_notes_only_the_dropped_modules_and_fails_on_the_rest(monkeypatch, tmp_path):
    stderr = ("top.v:3: error: Unknown module type: counter\n"
              "top.v:4: error: Unknown module type: countr\n")
    _iverilog(monkeypatch, stderr)
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="iverilog", scope_modules={"counter"})
    assert result["success"] is False
    messages = [d["message"] for d in result["diagnostics"]]
    assert any("countr" in m for m in messages)
    assert all("Unknown module type: counter" not in m for m in messages)
    assert len(result["notes"]) == 1 and "counter" in result["notes"][0] and "countr" not in result["notes"][0]


def test_file_scoped_verilator_keeps_a_module_no_dropped_file_defines(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout: {"returncode": 1, "stdout": "", "stderr": VERILATOR_MISSING_MODULE, "command": " ".join(cmd)},
    )
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is False and result["notes"] == []


def test_empty_scope_is_strict_lint(monkeypatch, tmp_path):
    """An override that drops nothing yields an empty module set — identical
    to the whole-design default."""
    _iverilog(monkeypatch, IVERILOG_MISSING_MODULE)
    for scope in (None, set(), frozenset()):
        result = rl.run_linter(["tb.v"], cwd=str(tmp_path), engine="iverilog", scope_modules=scope)
        assert result["success"] is False and result["notes"] == []


def test_split_unresolved_module_diagnostics_honors_scope():
    diags = rl.parse_iverilog_diagnostics(
        "top.v:3: error: Unknown module type: counter\ntop.v:4: error: Unknown module type: countr\n"
    )
    kept, missing = rl.split_unresolved_module_diagnostics(diags, {"counter"})
    assert missing == ["counter"]
    assert [d["message"] for d in kept] == ["Unknown module type: countr"]


def test_verilator_lints_exactly_the_files_it_is_given(monkeypatch, tmp_path):
    """Staging drive 2026-09-09: verilator treats -I dirs as module libraries,
    so linting rtl/top.v alone silently elaborated the unlisted rtl/alu.v beside
    it — the run was never file-scoped and the drop note ("not part of this
    run") was false. The command must switch module auto-discovery off while
    keeping -I for `include` resolution."""
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    def fake_run(cmd, cwd, timeout):
        captured["cmd"] = cmd
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cmd)}

    monkeypatch.setattr(rl, "_run", fake_run)
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.v").write_text("module top; alu u(); endmodule\n")
    (rtl / "alu.v").write_text("module alu; endmodule\n")
    rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator")
    cmd = captured["cmd"]
    libext = [a for a in cmd if a.startswith("+libext+")]
    assert libext == [f"+libext+{rl._NO_LIBRARY_EXT}"], cmd
    assert not rl._NO_LIBRARY_EXT.endswith((".v", ".sv")), "the library extension must match no source file"
    assert f"-I{rtl}" in cmd, "include resolution stays on"
    assert str(rtl / "alu.v") not in cmd, "the unlisted file is not added by us either"
