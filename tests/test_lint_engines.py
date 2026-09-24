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

    def fake_run(cmd, cwd, timeout, env_extra=None):
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

    def fake_run(cmd, cwd, timeout, env_extra=None):
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

# The real binary always closes with its total (finding 3: that total is what
# a forgiven non-zero exit is checked against).
VERILATOR_MISSING_MODULE = (
    "%Error: top.v:3:10: Cannot find file containing module: 'missing_mod'\n"
    "%Error: Exiting due to 1 error(s)\n"
)


def _iverilog(monkeypatch, stderr, returncode=1):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout, env_extra=None: {"returncode": returncode, "stdout": "", "stderr": stderr, "command": " ".join(cmd)},
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
        lambda cmd, cwd, timeout, env_extra=None: {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cmd)},
    )
    result = rl.run_linter(["a.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is True and result["notes"] == []


def test_file_scoped_verilator_missing_module_is_a_note_too(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout, env_extra=None: {"returncode": 1, "stdout": "", "stderr": VERILATOR_MISSING_MODULE, "command": " ".join(cmd)},
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
        lambda cmd, cwd, timeout, env_extra=None: {"returncode": 1, "stdout": "", "stderr": VERILATOR_MISSING_MODULE, "command": " ".join(cmd)},
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


# --- -I means include directories, not source directories ---------------------
#
# Staging drive 2026-09-09 (discrepancy A): verilator treats every -I directory
# as a module LIBRARY, so deriving -I from the source files' directories made
# "lint rtl/top.v" silently compile the unlisted rtl/alu.v beside it — a
# whole-design verdict with a false "not part of this run" note. Now -I names
# only the caller's include_dirs, `include resolves beside the including file
# (--relative-includes), and verilator is asked to list what it read (-MMD).

VERILATOR_MISSING_MODULE_5020 = """%Error: rtl/top.v:3:3: Cannot find file containing module: 'alu'
    3 |   alu u_alu(.a(a), .b(b), .y(y));
      |   ^~~
%Error: rtl/top.v:3:3: This may be because there's no search path specified with -I<dir>.
    3 |   alu u_alu(.a(a), .b(b), .y(y));
      |   ^~~
        ... Looked in:
             alu
             alu.v
             alu.sv
%Error: Exiting due to 2 error(s)
"""


def _capture_verilator(monkeypatch, depfile_text=None, returncode=0, stderr=""):
    """Fake the subprocess; optionally write a .d into the --Mdir verilator
    was given, the way the real binary does after a clean elaboration."""
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    def fake_run(cmd, cwd, timeout, env_extra=None):
        captured["cmd"] = cmd
        mdir = cmd[cmd.index("--Mdir") + 1]
        captured["mdir"] = mdir
        assert os.path.isdir(mdir), "verilator does not create --Mdir; the caller must"
        if depfile_text is not None:
            with open(os.path.join(mdir, "Vtop__ver.d"), "w") as f:
                f.write(depfile_text)
        return {"returncode": returncode, "stdout": "", "stderr": stderr, "command": " ".join(cmd)}

    monkeypatch.setattr(rl, "_run", fake_run)
    return captured


def _nested_design(tmp_path):
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.v").write_text('`include "defs.vh"\nmodule top(input [`W-1:0] a, b, output [`W-1:0] y);\n  alu u_alu(.a(a), .b(b), .y(y));\nendmodule\n')
    (rtl / "alu.v").write_text("module alu(input [7:0] a, b, output [7:0] y);\n  assign y = a + b;\nendmodule\n")
    (rtl / "defs.vh").write_text("`define W 8\n")
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "glob.vh").write_text("`define G 4\n")
    (rtl / "top2.v").write_text('`include "glob.vh"\nmodule top2(input [`G-1:0] a, output [`G-1:0] y);\n  assign y = a;\nendmodule\n')
    return rtl, inc


def test_verilator_command_names_include_dirs_not_source_dirs(monkeypatch, tmp_path):
    """The regression pin: no -I for the directory a SOURCE lives in (that is
    the library search that widened the compile), -I for each include_dir,
    --relative-includes for the design's own headers, -MMD/--Mdir for the
    read list. Fails on the pre-fix derivation (-I from source dirs)."""
    captured = _capture_verilator(monkeypatch)
    rtl, inc = _nested_design(tmp_path)
    rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator", include_dirs=["inc"])
    cmd = captured["cmd"]
    assert cmd[:9] == [
        "verilator", "--lint-only", "--timing", "-Wall", "-Wno-fatal",
        "-Wno-EOFNEWLINE", "-Wno-DECLFILENAME", "--relative-includes", "-MMD",
    ]
    assert cmd[9:11] == ["--Mdir", captured["mdir"]]
    assert [a for a in cmd if a.startswith("-I")] == ["-Iinc"], cmd
    assert f"-I{rtl}" not in cmd and "-Irtl" not in cmd, "a source directory must never be a library"
    assert str(rtl / "alu.v") not in cmd, "the unlisted file is not added by us either"
    assert cmd[-1] == str(rtl / "top.v")


def test_verilator_command_without_include_dirs_has_no_dash_i(monkeypatch, tmp_path):
    captured = _capture_verilator(monkeypatch)
    rtl, _ = _nested_design(tmp_path)
    rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator")
    assert not [a for a in captured["cmd"] if a.startswith("-I")]
    rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator", include_dirs=["", None])
    assert not [a for a in captured["cmd"] if a.startswith("-I")], "empty entries are not '-I'"


def test_iverilog_command_gets_the_same_include_dirs(monkeypatch, tmp_path):
    """Parity: iverilog's -I is include-only (its library search is -y, never
    passed), so the manifest's include directories go to both engines."""
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    captured = {}

    def fake_run(cmd, cwd, timeout, env_extra=None):
        captured["cmd"] = cmd
        return {"returncode": 0, "stdout": "", "stderr": "", "command": " ".join(cmd)}

    monkeypatch.setattr(rl, "_run", fake_run)
    result = rl.run_linter(["rtl/top.v"], cwd=str(tmp_path), engine="iverilog", include_dirs=["inc", "rtl"])
    assert captured["cmd"] == [
        "iverilog", "-t", "null", "-g2012", "-gsupported-assertions", "-Iinc", "-Irtl", "rtl/top.v",
    ]
    assert "filesRead" not in result, "iverilog is not asked what it read — not measured, not claimed"


def test_parse_verilator_depfile_normalizes_dedupes_and_sorts(tmp_path):
    ws = str(tmp_path)
    text = (
        f"/dev/null /tmp/lint_deps_x/Vtop__ver.d  : /usr/bin/verilator_bin {ws}/rtl/defs.vh \\\n"
        f" /usr/bin/verilator_bin /usr/share/verilator/include/verilated_std.sv rtl/alu.v rtl/defs.vh rtl/top.v {ws}/rtl/top.v \n"
    )
    assert rl.parse_verilator_depfile(text, ws) == [
        "/usr/bin/verilator_bin",
        "/usr/share/verilator/include/verilated_std.sv",
        "rtl/alu.v",
        "rtl/defs.vh",
        "rtl/top.v",
    ]
    assert rl.parse_verilator_depfile("garbage without a rule", ws) == []


def test_run_linter_verilator_reports_files_read_and_cleans_up(monkeypatch, tmp_path):
    captured = _capture_verilator(
        monkeypatch,
        depfile_text="/dev/null x/Vtop__ver.d  : /usr/bin/verilator_bin rtl/alu.v rtl/top.v\n",
    )
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator")
    assert result["filesRead"] == ["/usr/bin/verilator_bin", "rtl/alu.v", "rtl/top.v"]
    assert not os.path.exists(captured["mdir"]), "the throwaway --Mdir is removed"


def test_run_linter_verilator_omits_files_read_when_no_depfile_was_written(monkeypatch, tmp_path):
    """Measured on 5.020: any error leaves no .d. Absent means not measured —
    the key is left out rather than claiming an empty read list."""
    captured = _capture_verilator(monkeypatch, depfile_text=None, returncode=1, stderr=VERILATOR_MISSING_MODULE_5020)
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator")
    assert "filesRead" not in result
    assert result["success"] is False
    assert not os.path.exists(captured["mdir"])


def test_search_path_hint_travels_with_the_unresolved_module_error():
    """verilator 5.020 follows MODNOTFOUND with a second %Error at the same
    file:line ("This may be because there's no search path…"). Scoped, both go
    with the excuse; strict, both stay errors."""
    diags = rl.parse_verilator_diagnostics(VERILATOR_MISSING_MODULE_5020)
    assert len(diags) == 2
    kept, missing = rl.split_unresolved_module_diagnostics(diags, {"alu"})
    assert missing == ["alu"] and kept == []
    kept, missing = rl.split_unresolved_module_diagnostics(diags, {"other"})
    assert missing == [] and len(kept) == 2
    # The same hint after a DIFFERENT error (an include not found) stays.
    other = rl.parse_verilator_diagnostics(
        "%Error: rtl/top2.v:1:10: Cannot find include file: glob.vh\n"
        "%Error: rtl/top2.v:1:10: This may be because there's no search path specified with -I<dir>.\n"
    )
    kept, missing = rl.split_unresolved_module_diagnostics(other, {"alu"})
    assert missing == [] and len(kept) == 2


def test_file_scoped_verilator_5020_output_passes_with_note(monkeypatch, tmp_path):
    _capture_verilator(monkeypatch, returncode=1, stderr=VERILATOR_MISSING_MODULE_5020)
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is True
    assert result["diagnostics"] == []
    assert "alu" in result["notes"][0]


def test_files_compiled_unions_files_read_and_diagnostic_files():
    assert rl.files_compiled({}) == set()
    assert rl.files_compiled({"filesRead": ["rtl/top.v"], "diagnostics": [
        {"file": "lib/alu.v", "line": 2, "severity": "error", "message": "x", "code": None},
        {"file": None, "line": None, "severity": "error", "message": "y", "code": None},
    ]}) == {"rtl/top.v", "lib/alu.v"}


# --- the same, against the real binary ---------------------------------------

_real_verilator = pytest.mark.skipif(rl.shutil.which("verilator") is None, reason="verilator not installed")


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_file_scoped_lint_does_not_compile_the_neighbour(tmp_path):
    """(a) rtl/top.v alone: the unlisted rtl/alu.v beside it is NOT elaborated.
    Fails on the pre-fix -I derivation (verilator found alu.v as a library
    file: rc=0, no diagnostic, no note)."""
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is True, result
    assert any("File-scoped lint" in n and "alu" in n for n in result["notes"]), result["notes"]
    assert "rtl/alu.v" not in (result.get("filesRead") or [])
    # `include "defs.vh" resolved beside top.v with no -I at all.
    assert not [d for d in result["diagnostics"] if "defs.vh" in (d["message"] or "")]


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_strict_lint_of_one_file_reports_the_missing_module(tmp_path):
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator")
    assert result["success"] is False
    _, missing = rl.split_unresolved_module_diagnostics(result["diagnostics"])
    assert missing == ["alu"]
    assert "filesRead" not in result


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_whole_set_reports_every_file_read(tmp_path):
    """(b) both files: success, and filesRead names both plus the header."""
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v"), str(rtl / "alu.v")], cwd=str(tmp_path), engine="verilator")
    assert result["success"] is True, result
    files = result["filesRead"]
    assert {"rtl/top.v", "rtl/alu.v", "rtl/defs.vh"} <= set(files)
    assert files == sorted(set(files))
    assert all(not f.startswith(str(tmp_path)) for f in files), "workspace files are workspace-relative"


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_include_dir_resolves_a_header_elsewhere(tmp_path):
    """(c) rtl/top2.v includes inc/glob.vh: fails without -Iinc, resolves with it."""
    rtl, _ = _nested_design(tmp_path)
    without = rl.run_linter([str(rtl / "top2.v")], cwd=str(tmp_path), engine="verilator")
    assert without["success"] is False
    assert any("glob.vh" in (d["message"] or "") for d in without["diagnostics"])
    result = rl.run_linter([str(rtl / "top2.v")], cwd=str(tmp_path), engine="verilator", include_dirs=["inc"])
    assert result["success"] is True, result
    assert "inc/glob.vh" in result["filesRead"]


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_residual_widening_is_visible_in_files_read(tmp_path):
    """(d) an include directory that is ALSO a source directory: verilator's
    library search finds the dropped rtl/alu.v there — and filesRead says so,
    which is what lets the manifest-aware layer tell the truth about it."""
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter(
        [str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator",
        scope_modules={"alu"}, include_dirs=["rtl"],
    )
    assert result["success"] is True
    assert result["notes"] == [], "nothing was left unresolved, so nothing is excused"
    assert "rtl/alu.v" in result["filesRead"]
    assert "rtl/alu.v" in rl.files_compiled(result)


# --- a forgiven non-zero exit must be FULLY explained (PR #92 review, finding 3)
#
# Pre-fix: exit_ok = rc == 0 or bool(notes) — one excused unresolved module
# forgave the whole exit, so an error the parser never saw (a %Error with no
# file:line, a crash, a timeout) rode to success behind it. Now the engine's
# own total must be present and no larger than what the excused diagnostics
# cost in that engine's units (verilator: one per %Error line, hint included;
# iverilog: references + 1 for the root).

VERILATOR_MISSING_PLUS_UNPARSED = """%Error: rtl/top.v:3:3: Cannot find file containing module: 'alu'
%Error: rtl/top.v:3:3: This may be because there's no search path specified with -I<dir>.
%Error: Cannot find file containing module: nope.v
%Error: Exiting due to 3 error(s)
"""

# Measured on verilator 5.020: two unresolved modules share ONE hint -> 3.
VERILATOR_TWO_MISSING_5020 = """%Error: top.v:2:3: Cannot find file containing module: 'alu'
%Error: top.v:2:3: This may be because there's no search path specified with -I<dir>.
%Error: top.v:3:3: Cannot find file containing module: 'blk'
%Error: Exiting due to 3 error(s)
"""


def test_engine_error_total_regexes():
    assert rl.engine_error_total("verilator", VERILATOR_MISSING_MODULE_5020) == 2
    assert rl.engine_error_total("verilator", VERILATOR_TWO_MISSING_5020) == 3
    assert rl.engine_error_total("verilator", "%Error: a.v:3:1: syntax error\n%Error: Cannot continue\n") is None
    assert rl.engine_error_total("iverilog", IVERILOG_MISSING_MODULE) == 2
    assert rl.engine_error_total("iverilog", IVERILOG_MISSING_PLUS_SYNTAX) is None
    assert rl.engine_error_total("iverilog", "3 error(s) in post-elaboration processing.\n") is None


def test_excused_module_plus_unparsed_fatal_line_is_still_a_failure(monkeypatch, tmp_path):
    """The reviewer's sequence: alu is excused, but verilator also counted an
    error the parser dropped (no file:line). Pre-fix: success True."""
    _capture_verilator(monkeypatch, returncode=1, stderr=VERILATOR_MISSING_PLUS_UNPARSED)
    result = rl.run_linter(["rtl/top.v", "nope.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is False
    assert any("alu" in n for n in result["notes"])  # the excuse is still narrated…
    errs = [d for d in result["diagnostics"] if d["severity"] == "error"]
    assert len(errs) == 1 and errs[0]["code"] == "EXIT"  # …and the rest is an honest failure
    assert "nope.v" in errs[0]["message"] and "exited 1" in errs[0]["message"]


def test_iverilog_total_above_the_excused_references_is_a_failure(monkeypatch, tmp_path):
    stderr = IVERILOG_MISSING_MODULE.replace("2 error(s)", "3 error(s)")
    _iverilog(monkeypatch, stderr)
    result = rl.run_linter(["tb.v"], cwd=str(tmp_path), engine="iverilog", scope_modules={"alu"})
    assert result["success"] is False
    assert [d["code"] for d in result["diagnostics"]] == ["EXIT"]
    assert "3 error(s) during elaboration" in result["diagnostics"][0]["message"]


def test_excused_module_without_the_engine_total_stays_a_failure(monkeypatch, tmp_path):
    """No total = the engine did not finish normally (verilator prints none
    after "Cannot continue"); nothing vouches for the exit, so it stands."""
    _capture_verilator(monkeypatch, returncode=1,
                       stderr="%Error: top.v:3:10: Cannot find file containing module: 'missing_mod'\n")
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"missing_mod"})
    assert result["success"] is False
    assert "missing_mod" in result["notes"][0]
    assert result["diagnostics"][-1]["code"] == "EXIT"


def test_verilator_total_matching_two_excused_modules_and_one_hint_passes(monkeypatch, tmp_path):
    _capture_verilator(monkeypatch, returncode=1, stderr=VERILATOR_TWO_MISSING_5020)
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu", "blk"})
    assert result["success"] is True and result["diagnostics"] == []
    assert "alu" in result["notes"][0] and "blk" in result["notes"][0]
    # Excuse only one of them: the other stays an error AND the total no longer matches.
    result = rl.run_linter(["top.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is False
    assert any("blk" in (d["message"] or "") for d in result["diagnostics"])


def test_unparsed_non_zero_exit_is_never_silent(monkeypatch, tmp_path):
    """Strict lint, rc=1, nothing the parser recognises (a file that does not
    exist, on verilator): previously success=False with diagnostics=[] — a
    failure with no reason. Now the tail is the reason."""
    _capture_verilator(monkeypatch, returncode=1, stderr=(
        "%Error: Cannot find file containing module: nope.v\n"
        "%Error: This may be because there's no search path specified with -I<dir>.\n"
        "%Error: Exiting due to 2 error(s)\n"
    ))
    result = rl.run_linter(["nope.v"], cwd=str(tmp_path), engine="verilator")
    assert result["success"] is False
    assert len(result["diagnostics"]) == 1 and result["diagnostics"][0]["code"] == "EXIT"
    assert "nope.v" in result["diagnostics"][0]["message"]
    # A timeout is the same shape.
    monkeypatch.setattr(rl, "_run", lambda cmd, cwd, timeout, env_extra=None: {
        "returncode": -1, "stdout": "", "stderr": "Error: Linting timed out.", "command": "x"})
    result = rl.run_linter(["a.v"], cwd=str(tmp_path), engine="iverilog")
    assert result["success"] is False
    assert "timed out" in result["diagnostics"][0]["message"]


def test_exit_explained_by_excused_units():
    assert rl.exit_explained_by_excused("verilator", VERILATOR_MISSING_MODULE_5020, 2) is True
    assert rl.exit_explained_by_excused("verilator", VERILATOR_MISSING_MODULE_5020, 1) is False
    assert rl.exit_explained_by_excused("verilator", VERILATOR_MISSING_MODULE_5020, 0) is False
    assert rl.exit_explained_by_excused("iverilog", IVERILOG_MISSING_MODULE, 1) is True   # 2 == 1 + root
    assert rl.exit_explained_by_excused("iverilog", "3 error(s) during elaboration.\n", 1) is False
    assert rl.exit_explained_by_excused("iverilog", IVERILOG_MISSING_PLUS_SYNTAX, 1) is False


@pytest.mark.requires_eda
@_real_verilator
def test_real_verilator_excused_exit_matches_its_total(tmp_path):
    """rtl/top.v alone, alu excused: the real total (1 module + 1 hint = 2)
    equals what was excused, so the scoped lint still passes — and adding a
    file verilator cannot find (an error with no file:line the parser never
    sees) makes the same gesture fail instead of riding behind the excuse."""
    rtl, _ = _nested_design(tmp_path)
    result = rl.run_linter([str(rtl / "top.v")], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is True, result
    # 5.020 counts the "no search path" hint as its own %Error (total 2);
    # 5.048 prints it as a `...` continuation (total 1). Either way the total
    # is fully explained by what was excused, which is what the verdict needs.
    assert rl.engine_error_total("verilator", result["stderr"]) in (1, 2)
    result = rl.run_linter([str(rtl / "top.v"), "nope.v"], cwd=str(tmp_path), engine="verilator", scope_modules={"alu"})
    assert result["success"] is False, result
    assert any(d["code"] == "EXIT" and "nope.v" in d["message"] for d in result["diagnostics"]), result["diagnostics"]
