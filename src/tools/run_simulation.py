import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from src.tools.stdcells import get_asap7_compat_model_files, resolve_stdcell_models
from src.tools.synthesis_manager import get_run_dir


PASS_MARKER_DEFAULT = "TEST PASSED"


def _is_stdcell_cache_error(exc: Exception) -> bool:
    msg = str(exc or "")
    return ("Standard-cell cache missing" in msg) or ("No stdcell model files found" in msg)


def _stdcell_bootstrap_hint(cwd: str, platform: Optional[str]) -> str:
    pf = platform or "<platform>"
    stdcell_ws = _stdcell_workspace(cwd)
    return (
        "Standard-cell cache is missing or incomplete for post-synthesis simulation. "
        f"Bootstrap with: PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace \"{stdcell_ws}\" --platform {pf}. "
        'See README section "First-Run Standard-Cell Bootstrap".'
    )


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


def _extract_sky130_required_modules(netlist_path: str) -> List[str]:
    try:
        with open(netlist_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return []
    names = sorted(set(re.findall(r"\b(sky130_fd_sc_hd__[A-Za-z0-9_]+)\b", text)))
    return names


def _extract_asap7_required_modules(netlist_path: str) -> List[str]:
    try:
        with open(netlist_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return []
    return sorted(set(re.findall(r"\b([A-Za-z0-9_]+_ASAP7_75t_R)\b", text)))


def _collect_defined_modules(file_paths: List[str]) -> set[str]:
    mods: set[str] = set()
    pat = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b")
    for fpath in file_paths:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except Exception:
            continue
        for m in pat.finditer(txt):
            mods.add(m.group(1))
    return mods


def _stdcell_workspace(cwd: str) -> str:
    env_path = os.environ.get("RTL_STDCELL_WORKSPACE")
    if env_path:
        return os.path.abspath(env_path)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "workspace")


def _asap7_compat_stdcell_files(stdcells: List[str], netlist_path: str) -> List[str]:
    compat = get_asap7_compat_model_files()
    seq_file = None
    base = []
    for fpath in stdcells:
        name = os.path.basename(fpath)
        if name == "asap7sc7p5t_SEQ_RVT_TT_220101.v":
            seq_file = fpath
            continue
        if name in {"dff.v", "empty.v"}:
            continue
        base.append(fpath)

    required = set(_extract_asap7_required_modules(netlist_path))
    available = _collect_defined_modules(base + compat)
    missing = sorted([m for m in required if m not in available])
    if missing and seq_file:
        # If required modules are not covered by compat+base, fall back to full SEQ file.
        base.append(seq_file)
    return base + compat


def _compile(
    compile_files: List[str],
    output_executable: str,
    cwd: str,
    timeout: int,
) -> Dict[str, Any]:
    include_dirs = sorted({os.path.dirname(os.path.abspath(p)) for p in compile_files if p})
    include_args: List[str] = []
    for inc in include_dirs:
        include_args.extend(["-I", inc])
    filelist = None
    try:
        fd, filelist = tempfile.mkstemp(prefix="iverilog_", suffix=".f", dir=cwd, text=True)
        os.close(fd)
        with open(filelist, "w", encoding="utf-8") as f:
            for src in compile_files:
                # Normalize slashes for portable filelist parsing on Windows.
                f.write(os.path.abspath(src).replace("\\", "/") + "\n")
    except Exception as exc:
        if filelist:
            try:
                os.remove(filelist)
            except Exception:
                pass
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Failed to prepare compile file list: {exc}",
            "command": "iverilog (filelist generation)",
        }

    cmd = ["iverilog", "-g2012"] + include_args + ["-o", output_executable, "-f", filelist]
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if filelist:
            try:
                os.remove(filelist)
            except Exception:
                pass
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "Compilation timed out.",
            "command": " ".join(cmd),
        }
    except Exception as exc:
        if filelist:
            try:
                os.remove(filelist)
            except Exception:
                pass
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Compilation execution error: {exc}",
            "command": " ".join(cmd),
        }
    if filelist:
        try:
            os.remove(filelist)
        except Exception:
            pass

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


def _detect_failure_info(status: str, stdout: str, stderr: str) -> Dict[str, Optional[str]]:
    text = f"{stdout or ''}\n{stderr or ''}"
    low = text.lower()

    def _first_line(patterns: List[str]) -> Optional[str]:
        for line in text.splitlines():
            l = line.lower()
            if any(p in l for p in patterns):
                return line.strip()
        return None

    if status == "compile_failed":
        return {"failure_type": "compile", "first_failure_line": _first_line(["error", "undefined", "unknown module"]), "first_failure_snippet": None}

    if "timed out" in low:
        return {"failure_type": "timeout", "first_failure_line": _first_line(["timed out"]), "first_failure_snippet": None}
    if "$fatal" in low or "fatal" in low:
        return {"failure_type": "fatal", "first_failure_line": _first_line(["$fatal", "fatal"]), "first_failure_snippet": None}
    if "assert" in low:
        return {"failure_type": "assertion", "first_failure_line": _first_line(["assert", "assertion"]), "first_failure_snippet": None}

    if status == "sim_failed":
        return {"failure_type": "runtime", "first_failure_line": _first_line(["error", "fail"]), "first_failure_snippet": None}
    if status == "test_failed":
        return {"failure_type": "test_failed", "first_failure_line": _first_line(["fail", "error"]), "first_failure_snippet": None}
    return {"failure_type": None, "first_failure_line": None, "first_failure_snippet": None}


def run_simulation(
    verilog_files: Optional[List[str]] = None,
    top_module: str = "tb",
    cwd: Optional[str] = None,
    timeout: int = 60,
    mode: str = "rtl",
    run_id: Optional[str] = None,
    netlist_file: Optional[str] = None,
    platform: Optional[str] = None,
    sim_profile: str = "auto",
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
    stdcell_bootstrap_attempted = False
    stdcell_bootstrap_result: Optional[Dict[str, Any]] = None

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
            "failure_type": "compile",
            "first_failure_line": f"Unsupported simulation mode: {mode}",
            "first_failure_snippet": None,
        }
    if sim_profile not in {"auto", "pinned", "compat"}:
        return {
            "status": "compile_failed",
            "compile_returncode": -1,
            "sim_returncode": None,
            "pass_marker_found": False,
            "stdout_tail": "",
            "stderr_tail": f"Unsupported sim_profile: {sim_profile}. Supported: auto, pinned, compat.",
            "log_truncated": False,
            "unresolved_cells": [],
            "success": False,
            "failure_type": "compile",
            "first_failure_line": f"Unsupported sim_profile: {sim_profile}. Supported: auto, pinned, compat.",
            "first_failure_snippet": None,
        }
    effective_sim_profile = sim_profile

    if mode == "post_synth":
        resolved_netlist = netlist_file
        run_dir = None
        if run_id is not None or resolved_netlist is None or not platform:
            run_dir = get_run_dir(cwd, run_id)
            if run_dir is None and (resolved_netlist is None or not platform):
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
                    "failure_type": "compile",
                    "first_failure_line": f"Unknown run_id '{run_id}' and no latest run available.",
                    "first_failure_snippet": None,
                }

        if resolved_netlist is None and run_dir is not None:
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
                "failure_type": "compile",
                "first_failure_line": "Post-synth mode requires a valid synthesized netlist.",
                "first_failure_snippet": None,
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
                "failure_type": "compile",
                "first_failure_line": "Post-synth mode requires platform metadata to resolve stdcell models.",
                "first_failure_snippet": None,
            }
        if effective_sim_profile == "auto":
            effective_sim_profile = "compat" if platform == "asap7" else "pinned"

        try:
            stdcells, manifest = resolve_stdcell_models(_stdcell_workspace(cwd), platform)
        except Exception as exc:
            stdcells = []
            hint = _stdcell_bootstrap_hint(cwd, platform) if _is_stdcell_cache_error(exc) else ""
            msg = str(exc)
            if hint:
                msg = f"{msg}\n{hint}"
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": msg,
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
                "stdcell_bootstrap_attempted": stdcell_bootstrap_attempted,
                "stdcell_bootstrap_result": stdcell_bootstrap_result,
                "failure_type": "compile",
                "first_failure_line": msg,
                "first_failure_snippet": None,
            }

        stdcells_for_compile = list(stdcells)
        netlist_abs = os.path.abspath(resolved_netlist)
        if platform == "asap7" and effective_sim_profile == "compat":
            stdcells_for_compile = _asap7_compat_stdcell_files(stdcells_for_compile, netlist_abs)

        compile_files = compile_files + [netlist_abs] + stdcells_for_compile

        if platform == "sky130hd":
            required = set(_extract_sky130_required_modules(netlist_abs))
            if required:
                selected = []
                for fpath in stdcells_for_compile:
                    mod_name = os.path.splitext(os.path.basename(fpath))[0]
                    if mod_name in required:
                        selected.append(fpath)
                if selected:
                    compile_files = compile_files[: len(verilog_files) + 1] + selected

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
            "sim_profile": effective_sim_profile,
            "stdcell_bootstrap_attempted": stdcell_bootstrap_attempted,
            "stdcell_bootstrap_result": stdcell_bootstrap_result,
            "compile_command": comp.get("command"),
            "sim_command": None,
            **_detect_failure_info("compile_failed", comp.get("stdout", ""), comp.get("stderr", "")),
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
        "sim_profile": effective_sim_profile,
        "stdcell_bootstrap_attempted": stdcell_bootstrap_attempted,
        "stdcell_bootstrap_result": stdcell_bootstrap_result,
        "compile_command": comp.get("command"),
        "sim_command": sim.get("command"),
        **_detect_failure_info(status, sim.get("stdout", ""), sim.get("stderr", "")),
    }
