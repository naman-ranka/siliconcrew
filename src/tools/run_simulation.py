import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from src.tools.stdcells import get_asap7_compat_model_files, resolve_stdcell_models, stdcell_root


PASS_MARKER_DEFAULT = "TEST PASSED"


def _is_stdcell_cache_error(exc: Exception) -> bool:
    msg = str(exc or "")
    return ("Standard-cell cache missing" in msg) or ("No stdcell model files found" in msg)


def _stdcell_bootstrap_hint(platform: Optional[str]) -> str:
    pf = platform or "<platform>"
    root = stdcell_root()
    return (
        "Standard-cell models are missing for post-synthesis simulation. They ship "
        "baked into the backend image at the install root, so on a hosted or "
        "self-host deploy this should never happen — report it. For a local "
        "checkout, populate them with: "
        f'PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace "{root}" --platform {pf}.'
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
    top_module: str = "",
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

    # -s pins the simulation root. Without it iverilog elaborates EVERY
    # un-instantiated module as a root — with two testbenches in the workspace
    # both would run interleaved in one simulation. The chosen top makes
    # "simulate this testbench" true; unchosen TBs become dead code.
    top_args = ["-s", top_module] if top_module else []
    cmd = ["iverilog", "-g2012"] + include_args + top_args + ["-o", output_executable, "-f", filelist]
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
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run RTL or post-synthesis simulation with strict status contract.

    Status enum:
      - compile_failed
      - sim_failed
      - test_failed
      - test_passed

    ``workspace`` is the run-record root (where ``synth_runs/`` lives). Post-synth
    resolution — netlist + platform + stdcell set — is read from the synthesis
    run's sim contract under this root, NOT re-discovered from ``cwd``. It
    defaults to ``cwd`` so the non-isolated path (where cwd == workspace) is
    unchanged; the isolated path passes its real workspace while ``cwd`` stays
    the per-run exec dir.
    """
    if cwd is None:
        cwd = os.getcwd()
    if workspace is None:
        workspace = cwd

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
    # Honest echo of what post-synth resolution actually picked (invariant #4:
    # no hidden magic). None for rtl mode.
    resolved_run_id: Optional[str] = None
    resolved_netlist: Optional[str] = None
    stdcell_source: Optional[str] = None

    if mode == "post_synth":
        # Resolve the gate netlist + platform + stdcell set from the synthesis
        # run's authoritative sim contract (read from the WORKSPACE run record),
        # never by re-discovering state under the exec cwd (issue #52).
        from src.tools.sim_contract import resolve_post_synth, stdcell_recovery_action

        resolution, res_err = resolve_post_synth(
            workspace=workspace,
            run_id=run_id,
            netlist_file=netlist_file,
            platform=platform,
        )
        if res_err is not None:
            return {
                "status": "compile_failed",
                "compile_returncode": -1,
                "sim_returncode": None,
                "pass_marker_found": False,
                "stdout_tail": "",
                "stderr_tail": res_err.message,
                "log_truncated": False,
                "unresolved_cells": [],
                "success": False,
                "mode": mode,
                "outcome": res_err.code,
                "recovery": res_err.recovery,
                "resolved_run_id": None,
                "resolved_netlist": None,
                "stdcell_source": None,
                "failure_type": "compile",
                "first_failure_line": res_err.message,
                "first_failure_snippet": None,
            }

        resolved_netlist_abs = resolution.netlist_abs
        platform = resolution.platform
        resolved_run_id = resolution.resolved_run_id
        resolved_netlist = resolution.resolved_netlist
        stdcell_source = resolution.stdcell_source

        if effective_sim_profile == "auto":
            effective_sim_profile = "compat" if platform == "asap7" else "pinned"

        try:
            stdcells, manifest = resolve_stdcell_models(stdcell_root(), platform)
        except Exception as exc:
            stdcells = []
            is_cache_err = _is_stdcell_cache_error(exc)
            hint = _stdcell_bootstrap_hint(platform) if is_cache_err else ""
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
                "mode": mode,
                # Semantic outcome + a native recovery the IDE (button) and the
                # agent (tool call) can both invoke — not a shell command.
                "outcome": "stdcell_cache_missing" if is_cache_err else "compile_failed",
                "recovery": stdcell_recovery_action(platform) if is_cache_err else None,
                "resolved_run_id": resolved_run_id,
                "resolved_netlist": resolved_netlist,
                "stdcell_source": stdcell_source,
                "stdcell_bootstrap_attempted": stdcell_bootstrap_attempted,
                "stdcell_bootstrap_result": stdcell_bootstrap_result,
                "failure_type": "compile",
                "first_failure_line": msg,
                "first_failure_snippet": None,
            }

        stdcells_for_compile = list(stdcells)
        netlist_abs = resolved_netlist_abs
        if platform == "asap7" and effective_sim_profile == "compat":
            stdcells_for_compile = _asap7_compat_stdcell_files(stdcells_for_compile, netlist_abs)

        # Drop the design RTL the gate netlist replaces. The manifest's simulate
        # set is [design RTL, testbench]; compiling that RTL beside the gate
        # netlist declares the design module twice ("already declared") — the
        # exact failure post_synth exists to avoid. Keep only sources the
        # netlist does NOT itself define: the testbench (and any helper module
        # the netlist doesn't provide). The netlist is authoritative for every
        # module it declares.
        netlist_modules = _collect_defined_modules([netlist_abs])
        if netlist_modules:
            tb_files = [
                p for p in compile_files
                if not (_collect_defined_modules([p]) & netlist_modules)
            ]
        else:
            tb_files = list(compile_files)

        compile_files = tb_files + [netlist_abs] + stdcells_for_compile

        if platform == "sky130hd":
            required = set(_extract_sky130_required_modules(netlist_abs))
            if required:
                selected = []
                for fpath in stdcells_for_compile:
                    mod_name = os.path.splitext(os.path.basename(fpath))[0]
                    if mod_name in required:
                        selected.append(fpath)
                if selected:
                    compile_files = compile_files[: len(tb_files) + 1] + selected

    output_exec = os.path.join(cwd, f"{top_module}.out")
    comp = _compile(compile_files=compile_files, output_executable=output_exec, cwd=cwd, timeout=timeout, top_module=top_module)

    if comp["returncode"] != 0:
        unresolved_cells = _extract_unresolved_cells(comp.get("stderr", "")) if mode == "post_synth" else []
        stderr_tail = _tail_text(comp.get("stderr", ""), max_lines_per_stream, max_chars_per_stream)
        stdout_tail = _tail_text(comp.get("stdout", ""), max_lines_per_stream, max_chars_per_stream)
        return {
            "status": "compile_failed",
            "compile_returncode": comp["returncode"],
            "sim_returncode": None,
            "pass_marker_found": False,
            "pass_marker": pass_marker,
            "stdout_tail": stdout_tail["text"],
            "stderr_tail": stderr_tail["text"],
            "log_truncated": stdout_tail["truncated"] or stderr_tail["truncated"],
            "unresolved_cells": unresolved_cells,
            "success": False,
            "mode": mode,
            "outcome": "compile_failed",
            "recovery": None,
            "resolved_run_id": resolved_run_id,
            "resolved_netlist": resolved_netlist,
            "stdcell_source": stdcell_source,
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
        "pass_marker": pass_marker,
        "stdout_tail": stdout_tail["text"],
        "stderr_tail": stderr_tail["text"],
        "log_truncated": stdout_tail["truncated"] or stderr_tail["truncated"],
        "unresolved_cells": unresolved_cells,
        "success": status == "test_passed",
        "mode": mode,
        # Semantic outcome the agent branches on / the IDE renders; mirrors the
        # status enum on the happy path.
        "outcome": status,
        "recovery": None,
        "resolved_run_id": resolved_run_id,
        "resolved_netlist": resolved_netlist,
        "stdcell_source": stdcell_source,
        "sim_profile": effective_sim_profile,
        "stdcell_bootstrap_attempted": stdcell_bootstrap_attempted,
        "stdcell_bootstrap_result": stdcell_bootstrap_result,
        "compile_command": comp.get("command"),
        "sim_command": sim.get("command"),
        **_detect_failure_info(status, sim.get("stdout", ""), sim.get("stderr", "")),
    }
