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
    }
"""
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

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
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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


def run_linter(verilog_files, cwd=None, timeout=30, engine="auto"):
    """Lint ``verilog_files`` with the chosen engine.

    Returns the structured contract documented in the module docstring. The
    legacy keys (success/stdout/stderr/command) are preserved so existing
    consumers keep working unchanged.
    """
    if cwd is None:
        cwd = os.getcwd()

    resolved = resolve_engine(engine)
    if "error" in resolved:
        return {
            "success": False,
            "stdout": "",
            "stderr": resolved["error"],
            "command": f"lint --engine {engine}",
            "engine": None,
            "diagnostics": [{"file": None, "line": None, "severity": "error", "message": resolved["error"], "code": "ENGINE"}],
        }
    eng = resolved["engine"]

    if eng == "verilator":
        # -Wall: the point of using verilator; -Wno-fatal: report everything in
        # one pass instead of stopping at the first error class. EOFNEWLINE and
        # DECLFILENAME are pure style pedantry (trailing newline, file-must-
        # match-module-name) — noise, not design risk.
        include_dirs = sorted({os.path.dirname(os.path.abspath(p)) for p in verilog_files if p})
        include_args = [f"-I{d}" for d in include_dirs]
        # --timing: accept event/delay constructs (verilator 5+), so linting a
        # file set that includes a testbench doesn't die on NEEDTIMINGOPT.
        cmd = [
            "verilator", "--lint-only", "--timing", "-Wall", "-Wno-fatal",
            "-Wno-EOFNEWLINE", "-Wno-DECLFILENAME",
        ] + include_args + list(verilog_files)
        raw = _run(cmd, cwd, timeout)
        diagnostics = parse_verilator_diagnostics(raw["stderr"] + "\n" + raw["stdout"], cwd)
    else:
        # -t null: no code generation, just check; -g2012 for SystemVerilog.
        cmd = ["iverilog", "-t", "null", "-g2012"] + list(verilog_files)
        raw = _run(cmd, cwd, timeout)
        diagnostics = parse_iverilog_diagnostics(raw["stderr"], cwd)

    has_errors = any(d["severity"] == "error" for d in diagnostics)
    return {
        "success": raw["returncode"] == 0 and not has_errors,
        "stdout": raw["stdout"],
        "stderr": raw["stderr"],
        "command": raw["command"],
        "engine": eng,
        "diagnostics": diagnostics,
    }
