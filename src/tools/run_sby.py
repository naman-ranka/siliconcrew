"""Run SymbiYosys (SBY) formal verification through the ToolEngine seam.

Execution is delegated to ``get_tool_engine()``:
  * **docker** (local default): the ``siliconcrew-sby`` container (sby + yosys +
    a solver), named + hard-killed on timeout so a non-terminating proof cannot
    orphan a container.
  * **native** (hosted / Cloud Run): ``sby`` runs as a subprocess directly in the
    per-session workspace — no Docker. Needs ``sby`` + a solver (z3) on PATH,
    installed in the hosted image.

This module keeps its own command-building + status parsing; only *execution*
varies. The command is **cwd-relative** (`sby -f <file>` in the file's own
directory) so it runs identically under either engine.

NOTE: SBY needs a solver engine (z3/yices/boolector). The default `openroad/orfs`
image ships sby + yosys but NO external SMT solver, so real proofs ERROR until a
solver is present; the tool reports that honestly rather than hanging.
"""
from __future__ import annotations

import os

from src.platform_engines.tool_engine import get_tool_engine

# Derived from openroad/orfs + z3 (the base image has sby/yosys but NO solver). Build with:
#   docker build -t siliconcrew-sby:latest - < Dockerfile.sby
# Falls back behavior: if this image is absent, pass image="openroad/orfs:latest" (proofs will ERROR).
# sby files should use the `smtbmc z3` engine (z3 is the installed solver).
DEFAULT_SBY_IMAGE = "siliconcrew-sby:latest"
DEFAULT_TIMEOUT = 110                          # under codex's ~120s MCP tool-call limit


def run_sby(sby_file, cwd=None, timeout=DEFAULT_TIMEOUT, image=DEFAULT_SBY_IMAGE) -> dict:
    """Run `sby -f <file>` via the selected ToolEngine with a hard timeout.

    Returns: {success, status: PASS|FAIL|TIMEOUT|ERROR|UNKNOWN, timed_out, stdout,
              stderr, counter_example, command}
    """
    abs_sby = os.path.abspath(sby_file)
    if not os.path.exists(abs_sby):
        return _err(f"SBY file not found: {sby_file}")

    # Run in the .sby file's own directory (the per-session workspace); the
    # command references the file by basename so it is engine-agnostic.
    run_dir = os.path.dirname(abs_sby)
    sby_name = os.path.basename(abs_sby)
    command = f"sby -f {sby_name}"

    res = get_tool_engine().run(
        image=image, command=command, cwd=run_dir, timeout=timeout, name_prefix="sc_sby"
    )

    stdout = res.get("stdout", "") or ""
    stderr = res.get("stderr", "") or ""
    timed_out = bool(res.get("timed_out"))
    status = _classify(stdout + stderr, 0 if res.get("success") else 1, timed_out)
    return {
        "success": status == "PASS",
        "status": status,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "counter_example": None,
        "command": res.get("command", command),
    }


def _classify(out: str, rc: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    if "DONE (PASS" in out:
        return "PASS"
    if "DONE (FAIL" in out:
        return "FAIL"
    if "DONE (UNKNOWN" in out or "DONE (TIMEOUT" in out or "DONE (ERROR" in out:
        return "ERROR"
    if "ERROR:" in out or "Traceback (most recent call last)" in out or rc != 0:
        return "ERROR"
    return "UNKNOWN"


def _err(msg: str, command: str = "") -> dict:
    return {"success": False, "status": "ERROR", "timed_out": False,
            "stdout": "", "stderr": msg, "counter_example": None, "command": command}
