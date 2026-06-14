"""Run SymbiYosys (SBY) formal verification in a container — hardened.

Mirrors the robustness of the redesigned cocotb tool:
  * **Named container + guaranteed `docker kill` on timeout** — the old path went through
    run_docker_command, which kills the docker CLI but can ORPHAN the container; a long/non-terminating
    proof would keep running. Here the container is named and explicitly killed.
  * **Bounded timeout under the MCP client limit** (default 110s, was 300s > codex's ~120s) so we return
    a structured result instead of letting the client time out first. A timeout => status="TIMEOUT"
    (treat as not-proven), not an opaque hang.
  * **Structured status** parsed from sby's own DONE line: PASS / FAIL / TIMEOUT / ERROR / UNKNOWN.
  * **Synchronous** (the MCP server offloads tools to a thread executor, so blocking is fine).

NOTE: SBY needs a solver engine. The default `openroad/orfs` image ships sby + yosys + yosys-smtbmc but
NO external SMT solver (z3/yices/boolector) and no standalone abc — so real proofs may return ERROR until
a solver is added to the image or a solver-equipped image is passed via `image=`. The tool reports that
honestly rather than hanging.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid

try:
    from src.tools.run_docker import _translate_dood_path
except Exception:
    from tools.run_docker import _translate_dood_path

# Derived from openroad/orfs + z3 (the base image has sby/yosys but NO solver). Build with:
#   docker build -t siliconcrew-sby:latest - < Dockerfile.sby
# Falls back behavior: if this image is absent, pass image="openroad/orfs:latest" (proofs will ERROR).
# sby files should use the `smtbmc z3` engine (z3 is the installed solver).
DEFAULT_SBY_IMAGE = "siliconcrew-sby:latest"
DEFAULT_TIMEOUT = 110                          # under codex's ~120s MCP tool-call limit
_HOST_WORKSPACE = os.environ.get("HOST_WORKSPACE")


def _resolve_workspace(abs_path: str) -> tuple[str, str]:
    """Return (workspace_root, path_relative_to_root) by finding the workspace anchor in the path."""
    parts = abs_path.split(os.sep)
    for anchor in ("workspace_new", "workspace"):
        if anchor in parts:
            idx = parts.index(anchor)
            return os.sep.join(parts[: idx + 1]), os.sep.join(parts[idx + 1:])
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workspace"))
    try:
        return root, os.path.relpath(abs_path, root)
    except ValueError:
        return os.path.dirname(abs_path), os.path.basename(abs_path)


def run_sby(sby_file, cwd=None, timeout=DEFAULT_TIMEOUT, image=DEFAULT_SBY_IMAGE) -> dict:
    """Run `sby -f <file>` in a container with a hard timeout and guaranteed cleanup.

    Returns: {success, status: PASS|FAIL|TIMEOUT|ERROR|UNKNOWN, timed_out, stdout, stderr,
              counter_example, command}
    """
    abs_sby = os.path.abspath(sby_file)
    if not os.path.exists(abs_sby):
        return _err(f"SBY file not found: {sby_file}")
    if not shutil.which("docker"):
        return _err(f"Docker not found in PATH; SBY runs in the {image} container.")

    workspace_root, rel = _resolve_workspace(abs_sby)
    sby_dir = os.path.dirname(rel).replace("\\", "/")
    sby_name = os.path.basename(rel)
    mount = workspace_root
    if _HOST_WORKSPACE:  # DooD: translate to a host path for the sibling daemon
        mount = _translate_dood_path(mount)

    cd = f"/workspace/{sby_dir}" if sby_dir else "/workspace"
    inner = f"cd {cd} && sby -f {sby_name}"
    name = f"sc_sby_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    docker_cmd = [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{mount}:/workspace", "-w", "/workspace",
        image, "bash", "-c", inner,
    ]

    proc = None
    timed_out = False
    try:
        proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "kill", name], capture_output=True, text=True)  # kill the container, not just the CLI
        try:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
        rc = -1
    except Exception as e:
        return _err(f"Docker execution error: {e}", command=" ".join(docker_cmd))
    finally:
        if proc and proc.poll() is None:
            proc.kill()

    out = (stdout or "") + (stderr or "")
    status = _classify(out, rc, timed_out)
    return {
        "success": status == "PASS",
        "status": status,
        "timed_out": timed_out,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "counter_example": None,
        "command": " ".join(docker_cmd),
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
