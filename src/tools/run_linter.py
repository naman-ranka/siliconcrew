"""Lint — one interface, pluggable engines, ONE diagnostic contract.

Engines differ in what they CATCH, not in their shape: both take a file list
and emit ``file:line severity message`` diagnostics.

  * ``iverilog``  — syntax/elaboration check (``iverilog -t null``). The
                    compatibility floor; catches typos, not design smells.
  * ``verilator`` — ``verilator --lint-only -Wall``: the open-source standard
                    for real lint (inferred latches, width mismatches,
                    unsynthesizable constructs), each with a warning CODE
                    (WIDTH, LATCH, …).
  * ``auto``      — verilator when installed, else iverilog.

This module owns ALL diagnostic parsing (moved here from the REST layer so the
agent tool, the REST endpoint, and any future caller share one structured
contract instead of re-parsing stderr each their own way).

Return shape (legacy keys preserved for existing consumers, structured keys
added):

    {
      "success": bool,            # no errors (engine exit + diagnostics)
      "stdout": str, "stderr": str, "command": str,   # legacy
      "engine": "iverilog"|"verilator",               # what actually ran
      "diagnostics": [ {file, line, severity, message, code|None} ],
      "notes": [str],             # honest scope notes (see scope_modules below)
      "filesRead": [str],         # verilator only, and only when it completed
                                  # elaboration (see below); absent = not measured
    }

The file list IS the compile set; ``include_dirs`` are include directories.
The two must not be conflated: verilator treats every ``-I`` directory as a
module LIBRARY too (an unresolved ``alu`` is looked up as ``<dir>/alu.v``),
so deriving ``-I`` from the directories of the source files — which this
module once did — silently compiled unlisted files from beside listed ones
and made "lint this file" a whole-design verdict on verilator. Now ``-I``
names only the caller's include directories (the manifest's include-role
files' directories, in practice), and `` `include`` resolves relative to the
including file (``--relative-includes``) with no ``-I`` at all.

Because verilator can still widen the compile through an include directory
that also holds sources, it is asked to say what it read: ``-MMD --Mdir`` in
a throwaway directory yields a make-style ``.d`` naming every file the run
depended on — sources, includes, library hits, and verilator's own support
files. That list is ``filesRead`` (workspace-relative for files under ``cwd``,
absolute otherwise, deduped, sorted). verilator writes it only after a clean
elaboration (measured on 5.020: any error, including one inside a library-
found file, leaves no ``.d``), so ``filesRead`` is absent on a failed run and
absent on iverilog, which is not asked (its ``-M`` option is unverified here).
Absent means "not measured", never "read nothing".

``scope_modules`` says out loud what the caller already knows: the file set
being linted deliberately leaves out design files the manifest would have
supplied (the explorer's "lint THIS file" gesture), and THESE are the module
names those left-out files define (:func:`manifest.modules_defined_by`). Both
engines report a module that is instantiated but absent from the file set as
an ERROR ("Unknown module type" / "Cannot find file containing module") — a
true statement about the compile, but a FALSE verdict about the file the user
asked about when the module lives in a file they chose not to lint. Exactly
those diagnostics are removed and replaced by one note naming the modules
that were not elaborated. Nothing else is softened: a syntax error in the
linted file still fails, any other error diagnostic still fails, and an
unresolved module NO left-out file defines (a typo'd instantiation, a module
missing from the whole design) stays a failure — a note may only ever state
a fact the manifest knows, never a policy of trust.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Collection, Dict, List, Optional

ENGINES = ("auto", "iverilog", "verilator")

# iverilog stderr: "file.v:12: warning: ..." / "file.v:12: syntax error"
_IVERILOG_PAT = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)?\s*(?P<sev>error|warning|syntax error)?:?\s*(?P<msg>.*)$"
)

# verilator: "%Warning-WIDTH: file.v:12:5: ..." / "%Error: file.v:3: ..."
_VERILATOR_PAT = re.compile(
    r"^%(?P<sev>Warning|Error)(?:-(?P<code>[A-Z0-9_]+))?:\s*(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)?\s*(?P<msg>.*)$"
)


def _norm_file(raw: str, cwd: Optional[str]) -> str:
    """Workspace-relative when possible, else basename — what the UI's
    click-to-open expects."""
    raw = raw.strip()
    if cwd and os.path.isabs(raw):
        try:
            rel = os.path.relpath(raw, cwd)
            if not rel.startswith(".."):
                return rel.replace(os.sep, "/")
        except ValueError:
            pass
    return os.path.basename(raw) if os.path.isabs(raw) else raw.replace(os.sep, "/")


def parse_iverilog_diagnostics(stderr: str, cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in (stderr or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _IVERILOG_PAT.match(stripped)
        if not m:
            # Unattributed error lines still surface (e.g. "N error(s)" summaries
            # are skipped; genuine messages kept).
            if "error" in stripped.lower() and "error(s)" not in stripped.lower():
                out.append({"file": None, "line": None, "severity": "error", "message": stripped, "code": None})
            continue
        sev_raw = (m.group("sev") or "error").lower()
        out.append({
            "file": _norm_file(m.group("file"), cwd),
            "line": int(m.group("line")),
            "severity": "warning" if sev_raw == "warning" else "error",
            "message": m.group("msg").strip() or stripped,
            "code": None,
        })
    return out


def parse_verilator_diagnostics(output: str, cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in (output or "").splitlines():
        m = _VERILATOR_PAT.match(line.strip())
        if not m:
            continue
        out.append({
            "file": _norm_file(m.group("file"), cwd),
            "line": int(m.group("line")),
            "severity": "warning" if m.group("sev") == "Warning" else "error",
            "message": m.group("msg").strip(),
            "code": m.group("code"),
        })
    return out


# "This module is instantiated but is not in the file set I was given" — the
# ONE diagnostic class a deliberately file-scoped lint must not turn into a
# FAILED verdict. iverilog: "Unknown module type: alu"; verilator:
# "Cannot find file containing module: 'alu'" (code MODNOTFOUND on 5.x).
_UNRESOLVED_MODULE_PATS = (
    re.compile(r"^Unknown module type:\s*(?P<mod>\S+)"),
    re.compile(r"^Cannot find file containing module:\s*'?(?P<mod>[^'\s]+)'?"),
)

# verilator follows a not-found error with a second %Error at the SAME
# file:line — "This may be because there's no search path specified with
# -I<dir>." — a hint about the first, not a finding of its own. It travels
# with the unresolved-module error it explains (and only that one: the same
# hint after "Cannot find include file" stays, as that error stays).
_SEARCH_PATH_HINT_PAT = re.compile(r"^This may be because there's no search path specified")

# Each engine states its own error total on stderr. That total is what lets a
# file-scoped run judge a non-zero exit honestly: the exit is forgiven ONLY
# when the engine counted nothing beyond the diagnostics this module excused.
# An error the parser never saw — a "%Error:" with no file:line, a crash, a
# timeout — is still in the engine's count, so it can no longer hide behind an
# excused unresolved module.
#   verilator 5.020 (measured): "%Error: Exiting due to N error(s)". Every
#   %Error line counts one, the -I hint after an unresolved module included
#   (one module + hint = 2; two modules share one hint = 3). A parse failure
#   prints "%Error: Cannot continue" and NO total.
#   iverilog (elaborate.cc / main.cc; two real samples and the fixture agree):
#   "N error(s) during elaboration." with N = unresolved references + 1: the
#   root work item (elaborate_root_scope_t) adds one when the root's scope
#   elaboration reports des->errors != 0. That is one per root module whose
#   scope ran at or after the first error; the file-scoped gesture lints one
#   file, one root. A further root with errors of its own counts one more and
#   is judged unexplained — the strict direction, never the lenient one.
_ENGINE_ERROR_TOTAL_PATS = {
    "verilator": re.compile(r"^%Error: Exiting due to (?P<n>\d+) error", re.M),
    "iverilog": re.compile(r"^(?P<n>\d+) error\(s\) during elaboration\.", re.M),
}
_ENGINE_ERROR_TOTAL_SLACK = {"verilator": 0, "iverilog": 1}


def engine_error_total(engine: str, stderr: str) -> Optional[int]:
    """The error total the engine printed, or ``None`` when it printed none
    (verilator after a parse failure, a crash, a timeout)."""
    pat = _ENGINE_ERROR_TOTAL_PATS.get(engine)
    m = pat.search(stderr or "") if pat else None
    return int(m.group("n")) if m else None


def exit_explained_by_excused(engine: str, stderr: str, excused: int) -> bool:
    """Whether a non-zero exit is fully accounted for by the ``excused``
    diagnostics (those :func:`split_unresolved_module_diagnostics` removed,
    hints included): the engine's own total is present and no larger than
    what those diagnostics cost in that engine's units."""
    if excused <= 0:
        return False
    total = engine_error_total(engine, stderr)
    return total is not None and total <= excused + _ENGINE_ERROR_TOTAL_SLACK.get(engine, 0)


def _stderr_tail(stderr: str, n: int = 5) -> str:
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    return " | ".join(lines[-n:])


def split_unresolved_module_diagnostics(
    diagnostics: List[Dict[str, Any]],
    scope_modules: Optional[Collection[str]] = None,
):
    """Split ``diagnostics`` into (kept, missing_module_names).

    Only ERROR diagnostics matching the unresolved-module signatures move to
    the second list, and — when ``scope_modules`` is given — only those naming
    a module in that set. Warnings, every other error, and an unresolved
    module outside the set stay in ``kept``. ``None`` means "any name" (the
    parser-level split, no scope knowledge).
    """
    kept: List[Dict[str, Any]] = []
    missing: List[str] = []
    last_split = None  # (file, line) of the unresolved-module error just moved
    for d in diagnostics:
        name = None
        message = (d.get("message") or "").strip()
        if d.get("severity") == "error":
            if last_split == (d.get("file"), d.get("line")) and _SEARCH_PATH_HINT_PAT.match(message):
                continue  # the hint attached to the error that just moved
            for pat in _UNRESOLVED_MODULE_PATS:
                m = pat.match(message)
                if m:
                    name = m.group("mod").strip("'\"")
                    break
        if name is None or (scope_modules is not None and name not in scope_modules):
            kept.append(d)
            last_split = None
        else:
            last_split = (d.get("file"), d.get("line"))
            if name not in missing:
                missing.append(name)
    return kept, missing


def _rel_or_abs(path: str, cwd: str) -> str:
    """Workspace-relative POSIX for a file under ``cwd``; absolute otherwise."""
    absolute = os.path.abspath(os.path.join(cwd, path))
    rel = os.path.relpath(absolute, cwd)
    if rel == "." or rel.startswith(".."):
        return absolute
    return rel.replace(os.sep, "/")


def parse_verilator_depfile(text: str, cwd: str) -> List[str]:
    """The dependency list of a verilator ``-MMD`` file, normalized.

    Format (verilator 5.020, measured): one rule, ``<targets> : <dep> <dep>
    ...``, whitespace-separated, unescaped (a path containing a space would
    split — verilator does not quote them, so neither can this), possibly
    with ``\\``-newline continuations. Dependencies are whatever verilator
    wrote: the sources given, every `` `include``d file, every module found
    through a ``-I`` library search, and verilator's own support files and
    binary. Nothing is filtered — a reader who wants "workspace files only"
    keeps the relative entries.
    """
    body = text.replace("\\\n", " ")
    _, sep, deps = body.partition(":")
    if not sep:
        return []
    return sorted({_rel_or_abs(tok, cwd) for tok in deps.split() if tok})


def _read_verilator_depfiles(mdir: str, cwd: str) -> Optional[List[str]]:
    """``filesRead`` from a run's ``--Mdir``, or ``None`` when verilator wrote
    no ``.d`` (it does so only after a clean elaboration)."""
    paths = sorted(glob.glob(os.path.join(mdir, "*.d")))
    if not paths:
        return None
    files: set = set()
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            files.update(parse_verilator_depfile(fh.read(), cwd))
    return sorted(files)


def files_compiled(result: Dict[str, Any]) -> set:
    """Files a lint result PROVES the engine read: ``filesRead`` when it was
    measured, plus every file a diagnostic is attributed to (an engine cannot
    report ``x.v:12`` without having read ``x.v`` — this is what still tells
    the truth on a failed verilator run, where no ``.d`` is written)."""
    files = set(result.get("filesRead") or ())
    files.update(d["file"] for d in (result.get("diagnostics") or ()) if d.get("file"))
    return files


def resolve_engine(engine: str = "auto") -> Dict[str, Any]:
    """Pick the engine to run. Honest failure when an explicit choice is missing."""
    engine = (engine or "auto").lower()
    if engine not in ENGINES:
        return {"error": f"Unknown lint engine '{engine}'. Choose one of: {', '.join(ENGINES)}."}
    have_verilator = shutil.which("verilator") is not None
    have_iverilog = shutil.which("iverilog") is not None
    if engine == "auto":
        if have_verilator:
            return {"engine": "verilator"}
        if have_iverilog:
            return {"engine": "iverilog"}
        return {"error": "No lint engine installed (need verilator or iverilog in PATH)."}
    if engine == "verilator" and not have_verilator:
        return {"error": "Lint engine 'verilator' is not installed on this server."}
    if engine == "iverilog" and not have_iverilog:
        return {"error": "Lint engine 'iverilog' is not installed on this server."}
    return {"engine": engine}


def _run(cmd: List[str], cwd: str, timeout: int) -> Dict[str, Any]:
    proc = None
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        stdout, stderr = proc.communicate(timeout=timeout)
        return {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr, "command": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        return {"returncode": -1, "stdout": "", "stderr": "Error: Linting timed out.", "command": " ".join(cmd)}
    except Exception as e:
        if proc:
            proc.kill()
        return {"returncode": -1, "stdout": "", "stderr": f"Execution Error during linting: {e}", "command": " ".join(cmd)}
    finally:
        if proc and proc.poll() is None:
            proc.kill()


def run_linter(
    verilog_files,
    cwd=None,
    timeout=30,
    engine="auto",
    scope_modules: Optional[Collection[str]] = None,
    include_dirs: Optional[Collection[str]] = None,
):
    """Lint ``verilog_files`` with the chosen engine.

    ``scope_modules``: the module names defined by design files the caller
    deliberately left out of this file set (see the module docstring). An
    unresolved-module error naming one of them is reported as a note instead
    of a failure; every other unresolved module remains an error. ``None`` or
    empty = strict lint, the default — so the agent / MCP path (which chooses
    its own file set and is told to include the dependencies) keeps today's
    behavior exactly.

    ``include_dirs``: directories (relative to ``cwd`` or absolute) searched
    for `` `include`` files that do not resolve relative to the including
    file — the manifest's include-role directories, in practice. They are
    passed to BOTH engines as ``-I`` (iverilog's ``-I`` is include-only, so
    there it is pure parity). The source files' own directories are NOT added
    (module docstring: on verilator that would turn the file list into a
    whole-design compile).

    Returns the structured contract documented in the module docstring. The
    legacy keys (success/stdout/stderr/command) are preserved so existing
    consumers keep working unchanged.
    """
    if cwd is None:
        cwd = os.getcwd()
    include_args = [f"-I{d}" for d in (include_dirs or ()) if d]
    files_read: Optional[List[str]] = None

    resolved = resolve_engine(engine)
    if "error" in resolved:
        return {
            "success": False,
            "stdout": "",
            "stderr": resolved["error"],
            "command": f"lint --engine {engine}",
            "engine": None,
            "diagnostics": [{"file": None, "line": None, "severity": "error", "message": resolved["error"], "code": "ENGINE"}],
            "notes": [],
        }
    eng = resolved["engine"]

    if eng == "verilator":
        # -Wall: the point of using verilator; -Wno-fatal: report everything in
        # one pass instead of stopping at the first error class. EOFNEWLINE and
        # DECLFILENAME are pure style pedantry (trailing newline, file-must-
        # match-module-name) — noise, not design risk.
        # --timing: accept event/delay constructs (verilator 5+), so linting a
        # file set that includes a testbench doesn't die on NEEDTIMINGOPT.
        # --relative-includes: `include "x.vh" resolves beside the including
        # file, so a design's own headers need no -I — and -I is reserved for
        # the caller's include_dirs (module docstring: -I is also a module
        # library on verilator, so it must never name a source directory).
        # -MMD --Mdir <throwaway>: have verilator list every file it read
        # (filesRead) instead of us guessing. The directory must pre-exist
        # (verilator does not create it) and is searched as a library too,
        # which is harmless because it is empty.
        mdir = tempfile.mkdtemp(prefix="lint_deps_")
        try:
            cmd = [
                "verilator", "--lint-only", "--timing", "-Wall", "-Wno-fatal",
                "-Wno-EOFNEWLINE", "-Wno-DECLFILENAME", "--relative-includes",
                "-MMD", "--Mdir", mdir,
            ] + include_args + list(verilog_files)
            raw = _run(cmd, cwd, timeout)
            files_read = _read_verilator_depfiles(mdir, cwd)
        finally:
            shutil.rmtree(mdir, ignore_errors=True)
        diagnostics = parse_verilator_diagnostics(raw["stderr"] + "\n" + raw["stdout"], cwd)
    else:
        # -t null: no code generation, just check; -g2012 for SystemVerilog.
        # -gsupported-assertions: without it, RTL carrying an inline
        # `assert property` fails LINT outright ("sorry: concurrent_assertion_item
        # not supported") — the file is fine, iverilog just can't elaborate that
        # construct. Same flag and same reasoning as the sim compile; immediate
        # assertions are unaffected either way (lint never runs them).
        # -I<dir>: include search path only (iverilog's library search is -y,
        # which is never passed) — the same include_dirs verilator gets.
        cmd = ["iverilog", "-t", "null", "-g2012", "-gsupported-assertions"] + include_args + list(verilog_files)
        raw = _run(cmd, cwd, timeout)
        diagnostics = parse_iverilog_diagnostics(raw["stderr"], cwd)

    notes: List[str] = []
    excused = 0
    if scope_modules:
        parsed = diagnostics
        diagnostics, missing = split_unresolved_module_diagnostics(diagnostics, frozenset(scope_modules))
        excused = len(parsed) - len(diagnostics)
        if missing:
            notes.append(
                "File-scoped lint: "
                + ", ".join(missing)
                + " instantiated but not in the linted file set — external modules were not "
                "elaborated. Lint the whole design to check them."
            )

    has_errors = any(d["severity"] == "error" for d in diagnostics)
    # The engine's exit code counted the errors just explained away, so a
    # file-scoped run judges itself on what is LEFT — but only when the
    # engine's own total says nothing else was counted (see
    # exit_explained_by_excused). A non-zero exit nothing accounts for is a
    # failure that SAYS so: the stderr tail becomes the diagnostic rather than
    # a bare success=False with an empty list.
    rc = raw["returncode"]
    exit_ok = rc == 0 or exit_explained_by_excused(eng, raw["stderr"], excused)
    if not exit_ok and not has_errors:
        diagnostics.append({
            "file": None, "line": None, "severity": "error", "code": "EXIT",
            "message": f"{eng} exited {rc} with errors this lint did not account for: "
                       f"{_stderr_tail(raw['stderr']) or '(no stderr)'}",
        })
        has_errors = True
    out = {
        "success": exit_ok and not has_errors,
        "stdout": raw["stdout"],
        "stderr": raw["stderr"],
        "command": raw["command"],
        "engine": eng,
        "diagnostics": diagnostics,
        "notes": notes,
    }
    if files_read is not None:  # absent = not measured (module docstring)
        out["filesRead"] = files_read
    return out
