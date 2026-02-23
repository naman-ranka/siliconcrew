import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from src.tools.stdcells import resolve_stdcell_models
from src.tools.synthesis_manager import get_run_dir


PASS_MARKER_DEFAULT = "TEST PASSED"


def _tail_text(text: str, max_lines: int, max_chars: int) -> Dict[str, Any]:
    lines = text.splitlines()
    truncated = len(lines) > max_lines or len(text) > max_chars
    tail_lines = lines[-max_lines:] if lines else []
    out = "\n".join(tail_lines)
    if len(out) > max_chars:
        out = out[-max_chars:]
        truncated = True
    return {"text": out, "truncated": truncated}


def _extract_unresolved_cells(stderr: str) -> List[str]:
    patterns = [
        re.compile(r"Unknown module type:\s*([a-zA-Z_][\w$]*)", re.IGNORECASE),
        re.compile(r"module\s+([a-zA-Z_][\w$]*)\s+is\s+undefined", re.IGNORECASE),
        re.compile(r"Unresolved\s+module\s+([a-zA-Z_][\w$]*)", re.IGNORECASE),
    ]
    found = set()
    for pat in patterns:
        for m in pat.finditer(stderr or ""):
            found.add(m.group(1))
    return sorted(found)


def _compile(
    compile_files: List[str],
    output_executable: str,
    cwd: str,
    timeout: int,
) -> Dict[str, Any]:
    cmd = ["iverilog", "-g2012", "-o", output_executable] + compile_files
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "Compilation timed out.",
            "command": " ".join(cmd),
        }
    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Compilation execution error: {exc}",
            "command": " ".join(cmd),
        }

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(cmd),
    }


def _simulate(output_executable: str, cwd: str, timeout: int) -> Dict[str, Any]:
    cmd = ["vvp", output_executable]
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Simulation timed out.", "command": " ".join(cmd)}
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": f"Simulation execution error: {exc}", "command": " ".join(cmd)}

    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "command": " ".join(cmd)}


def run_simulation(
    verilog_files: Optional[List[str]] = None,
    top_module: str = "tb",
    cwd: Optional[str] = None,
    timeout: int = 60,
    mode: str = "rtl",
    run_id: Optional[str] = None,
    netlist_file: Optional[str] = None,
    platform: Optional[str] = None,
    pass_marker: str = PASS_MARKER_DEFAULT,
    max_lines_per_stream: int = 40,
    max_chars_per_stream: int = 4000,
) -> Dict[str, Any]:
    """
    Run RTL or post-synthesis simulation with strict status contract.

    Status enum:
      - compile_failed
      - sim_failed
      - test_failed
      - test_passed
    """
    if cwd is None:
        cwd = os.getcwd()

    verilog_files = verilog_files or []
    compile_files = [os.path.abspath(p) for p in verilog_files]
    status = "compile_failed"
    unresolved_cells: List[str] = []

    if mode not in {"rtl", "post_synth"}:
        return {
            "status": "compile_failed",
            "compile_returncode": -1,
            "sim_returncode": None,
            "pass_marker_found": False,
            "stdout_tail": "",
            "stderr_tail": f"Unsupported simulation mode: {mode}",
            "log_truncated": False,
            "unresolved_cells": [],
            "success": False,
        }

    if mode == "post_synth":
        run_dir = get_run_dir(cwd, run_id)
        if run_dir is None:
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": f"Unknown run_id '{run_id}' and no latest run available.",
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
            }

        resolved_netlist = netlist_file
        if resolved_netlist is None:
            meta_path = os.path.join(run_dir, "run_meta.json")
            if os.path.exists(meta_path):
                import json

                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                resolved_netlist = meta.get("netlist_path")
                platform = platform or meta.get("platform")

        if not resolved_netlist or not os.path.exists(resolved_netlist):
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": "Post-synth mode requires a valid synthesized netlist (resolved from run_id or netlist_file).",
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
            }

        if not platform:
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": "Post-synth mode requires platform metadata to resolve stdcell models.",
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
            }

        try:
            stdcells, manifest = resolve_stdcell_models(cwd, platform)
        except Exception as exc:
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": str(exc),
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
            }

        compile_files = compile_files + [os.path.abspath(resolved_netlist)] + stdcells

    output_exec = os.path.join(cwd, f"{top_module}.out")
    comp = _compile(compile_files=compile_files, output_executable=output_exec, cwd=cwd, timeout=timeout)

    if comp["returncode"] != 0:
        unresolved_cells = _extract_unresolved_cells(comp.get("stderr", "")) if mode == "post_synth" else []
        stderr_tail = _tail_text(comp.get("stderr", ""), max_lines_per_stream, max_chars_per_stream)
        stdout_tail = _tail_text(comp.get("stdout", ""), max_lines_per_stream, max_chars_per_stream)
        return {
            "status": "compile_failed",
            "compile_returncode": comp["returncode"],
            "sim_returncode": None,
            "pass_marker_found": False,
            "stdout_tail": stdout_tail["text"],
            "stderr_tail": stderr_tail["text"],
            "log_truncated": stdout_tail["truncated"] or stderr_tail["truncated"],
            "unresolved_cells": unresolved_cells,
            "success": False,
            "mode": mode,
            "compile_command": comp.get("command"),
            "sim_command": None,
        }

    sim = _simulate(output_executable=output_exec, cwd=cwd, timeout=timeout)
    stdout_tail = _tail_text(sim.get("stdout", ""), max_lines_per_stream, max_chars_per_stream)
    stderr_tail = _tail_text(sim.get("stderr", ""), max_lines_per_stream, max_chars_per_stream)

    pass_marker_found = pass_marker in (sim.get("stdout") or "")

    if sim["returncode"] != 0:
        status = "sim_failed"
    elif pass_marker_found:
        status = "test_passed"
    else:
        status = "test_failed"

    return {
        "status": status,
        "compile_returncode": comp["returncode"],
        "sim_returncode": sim["returncode"],
        "pass_marker_found": pass_marker_found,
        "stdout_tail": stdout_tail["text"],
        "stderr_tail": stderr_tail["text"],
        "log_truncated": stdout_tail["truncated"] or stderr_tail["truncated"],
        "unresolved_cells": unresolved_cells,
        "success": status == "test_passed",
        "mode": mode,
        "compile_command": comp.get("command"),
        "sim_command": sim.get("command"),
    }
