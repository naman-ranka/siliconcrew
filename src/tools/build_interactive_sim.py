"""Interactive web-sim netlist builder — Phase 0 of the interactive web
simulation wave.

Produces ONE self-describing artifact, ``<top>.websim.json``::

    {
      "format": "siliconcrew-websim-v1",
      "top": "counter",
      "generated_at": "2026-07-10T18:00:00+00:00",   # aware UTC
      "sources": {"counter.v": "<sha256 of the file bytes>"},
      "ports": [{"name": "clk", "direction": "input", "bits": 1}, ...],
      "yosys_netlist": { ...verbatim `write_json` output... }
    }

The frontend converts ``yosys_netlist`` with yosys2digitaljs/core and runs it
in digitaljs' HeadlessCircuit entirely in the browser — the backend does no
work at view time (the workspace is the database; hosted gets this for free).

``sources`` carries the staleness contract: the viewer re-hashes the current
source bytes and shows "stale — regenerate" on mismatch. Content hashes,
never mtimes — ``shutil.copy2`` preserves mtimes across template forks, so
mtime-based staleness misfires on every fork.

Engine selection mirrors run_linter: native ``yosys`` when installed (the
backend image ships it, so hosted works natively), else the local Docker
image; an honest error when neither is available.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.utils.paths import is_within

ARTIFACT_FORMAT = "siliconcrew-websim-v1"

# Filenames become yosys script tokens; keep them boring so a name can't
# smuggle extra yosys commands or shell syntax into either engine.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._/-]+$")
_SAFE_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

_YOSYS_TIMEOUT_SEC = 120


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_engine() -> Dict[str, str]:
    """Native yosys when installed; local Docker fallback; honest error."""
    if shutil.which("yosys"):
        return {"engine": "native"}
    from src.platform_engines.settings import get_settings

    if not get_settings().hosted:
        return {"engine": "docker"}
    return {"error": "yosys is not installed on this instance."}


def _yosys_script(
    rel_files: List[str],
    top_module: str,
    json_out: str,
    parameters: Optional[Dict[str, int]] = None,
) -> str:
    reads = "; ".join(f"read_verilog {f}" for f in rel_files)
    # Timing-constant overrides (the CLK_FREQ parameter idiom): RTL written
    # for a real clock counts real milliseconds; the browser engine sustains
    # ~1-10 kHz, so a design like simon_game (50 ticks/ms) is unplayable at
    # its default parameter. `hierarchy -chparam` elaborates the top with the
    # override — same mechanism its own testbench uses to simulate fast.
    chparams = "".join(
        f" -chparam {name} {value}" for name, value in (parameters or {}).items()
    )
    # Designs with inferred memories need two extra passes: the browser engine
    # rejects raw $memrd/$memwr pairs, so `memory -nomap` collects them into
    # the $mem cells it simulates natively (O(1) per access — mapping to
    # flops+muxes instead measured 18x slower); and `wreduce` first narrows
    # addresses so a 32-bit index constant (`seq[0] <= ...`) can't force
    # ABITS=32, which overflows the engine's address arithmetic. Both are
    # no-ops for memory-less designs.
    return (
        f"{reads}; hierarchy{chparams} -top {top_module}; proc; opt; "
        f"wreduce; memory -nomap; opt; write_json {json_out}"
    )


def _run_yosys(script: str, cwd: str, engine: str) -> Dict[str, Any]:
    """Run one yosys -p script; returns {success, stderr}."""
    if engine == "native":
        try:
            proc = subprocess.run(
                ["yosys", "-p", script],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_YOSYS_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "stderr": f"yosys timed out after {_YOSYS_TIMEOUT_SEC}s"}
        return {"success": proc.returncode == 0, "stderr": proc.stderr or proc.stdout}

    from src.tools.run_docker import run_docker_command

    # The script uses workspace-relative paths, and run_docker_command's
    # default container cwd is /OpenROAD-flow-scripts/flow — run in the
    # /workspace mount or read_verilog/write_json miss the workspace entirely.
    result = run_docker_command(
        command=f"yosys -p '{script}'", workspace_path=cwd, cwd="/workspace"
    )
    return {"success": result["success"], "stderr": result.get("stderr", "")}


def extract_ports(netlist: Dict[str, Any], top_module: str) -> Optional[List[Dict[str, Any]]]:
    mod = (netlist.get("modules") or {}).get(top_module)
    if mod is None:
        return None
    ports = []
    for name, p in (mod.get("ports") or {}).items():
        ports.append(
            {
                "name": name,
                "direction": p.get("direction", "input"),
                "bits": len(p.get("bits") or []),
            }
        )
    return ports


def build_websim_netlist(
    verilog_files: List[str],
    top_module: str,
    cwd: str,
    parameters: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Compile RTL to the websim artifact. Returns
    {success, artifact, ports, engine} or {success: False, error}.

    ``parameters`` overrides top-module parameters at elaboration (integers
    only — for timing constants like TICKS_PER_MILLI/CLK_FREQ so the design
    runs at browser-simulation speed). Overrides are recorded verbatim in the
    artifact: the netlist is honestly labeled as compiled with them.
    """
    if not verilog_files:
        return {"success": False, "error": "No Verilog files given."}
    if not _SAFE_MODULE.match(top_module or ""):
        return {"success": False, "error": f"Invalid top module name: {top_module!r}"}
    for name, value in (parameters or {}).items():
        if not _SAFE_MODULE.match(name or ""):
            return {"success": False, "error": f"Invalid parameter name: {name!r}"}
        if not isinstance(value, int) or isinstance(value, bool):
            return {
                "success": False,
                "error": f"Parameter {name} must be an integer, got {value!r}.",
            }

    rel_files: List[str] = []
    for item in verilog_files:
        rel = item.replace(os.sep, "/")
        if not _SAFE_NAME.match(rel):
            return {"success": False, "error": f"Unsupported characters in file name: {item!r}"}
        abs_path = os.path.join(cwd, rel)
        if not is_within(cwd, abs_path):
            return {"success": False, "error": f"File escapes the workspace: {item!r}"}
        if not os.path.isfile(abs_path):
            return {"success": False, "error": f"File {rel} does not exist."}
        rel_files.append(rel)

    picked = pick_engine()
    if "error" in picked:
        return {
            "success": False,
            "error": f"No yosys engine available: {picked['error']} "
            "Interactive simulation needs yosys (native or Docker).",
        }
    engine = picked["engine"]

    json_tmp = f"{top_module}.websim.netlist.tmp.json"
    script = _yosys_script(rel_files, top_module, json_tmp, parameters)
    ran = _run_yosys(script, cwd, engine)
    tmp_path = os.path.join(cwd, json_tmp)
    try:
        if not ran["success"]:
            return {"success": False, "error": f"Yosys failed: {ran['stderr'][-2000:]}"}
        if not os.path.isfile(tmp_path):
            return {"success": False, "error": "Yosys finished but wrote no netlist JSON."}
        with open(tmp_path, "r") as f:
            netlist = json.load(f)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    ports = extract_ports(netlist, top_module)
    if ports is None:
        return {
            "success": False,
            "error": f"Module '{top_module}' not found in the netlist "
            f"(modules: {sorted((netlist.get('modules') or {}).keys())}).",
        }

    artifact_name = f"{top_module}.websim.json"
    payload = {
        "format": ARTIFACT_FORMAT,
        "top": top_module,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {rel: _sha256_file(os.path.join(cwd, rel)) for rel in rel_files},
        "ports": ports,
        "yosys_netlist": netlist,
    }
    if parameters:
        # honesty: the sim runs THIS elaboration, not the source defaults —
        # the viewer surfaces the overrides in the provenance strip
        payload["parameters"] = dict(parameters)
    with open(os.path.join(cwd, artifact_name), "w") as f:
        json.dump(payload, f)

    return {"success": True, "artifact": artifact_name, "ports": ports, "engine": engine}
