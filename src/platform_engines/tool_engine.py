"""ToolEngine — the seam for *how* the light EDA tools execute.

Synthesis (ORFS) already runs cloud-safe via :mod:`orfs_runner`. The three
lighter engines — XLS (DSLX→Verilog), SymbiYosys (formal), cocotb — still shell
out to Docker, which does not work on Cloud Run (no nested containers). This
module puts their *execution* behind one small, config-selected interface,
mirroring the ``OrfsRunner`` pattern:

  * :class:`DockerToolEngine` — today's behavior: run the command in a container
    via :func:`src.tools.run_docker.run_docker_command` (the local default, so
    open-source contributors stay plug-and-play).
  * :class:`NativeToolEngine` — run the command directly as a subprocess in the
    real per-session workspace ``cwd`` (hosted / Cloud Run; ~no overhead, keeps
    the interactive edit-run loop fast).

Chosen once by the ``SIM_ENGINE`` setting (``native`` when hosted, else
``docker``). The tool files keep ALL their own command-building + output parsing
and call ``get_tool_engine().run(...)`` — there is **no** ``if hosted`` branch in
the tools.

The one real care-point is **paths**: Docker mounts the workspace at
``/workspace`` and runs there; native runs in the real ``cwd``. So each tool's
command must be **cwd-relative** (no absolute ``/workspace`` paths). The result
is a dict with the same shape the tools already consume
(``success/stdout/stderr/command`` + ``timed_out``).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import uuid
from typing import Dict, Optional, Protocol


# A tool execution result — a plain dict so call sites that mutate it
# (e.g. run_xls's `_with_stage` setdefault) keep working unchanged.
ToolResult = Dict[str, object]


def _result(success: bool, stdout: str, stderr: str, command: str, timed_out: bool = False) -> ToolResult:
    return {
        "success": success,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "command": command,
        "timed_out": timed_out,
    }


class ToolEngine(Protocol):
    mode: str

    def run(
        self,
        *,
        image: str,
        command: str,
        cwd: str,
        env: Optional[dict] = None,
        timeout: int,
        workdir: str = "/workspace",
        name_prefix: str = "sc_tool",
        base_env: Optional[dict] = None,
    ) -> ToolResult:
        ...


class DockerToolEngine:
    """Run the command in a container — today's local behavior (plug-and-play).

    Wraps :func:`run_docker_command` so the docker path is exactly today's
    (mountable, mock-verifiable), with optional ``-e env`` + a named container
    that is hard-killed on timeout. ``cwd`` (the real per-session workspace) is
    mounted at ``workdir`` (default ``/workspace``); the command runs there with
    cwd-relative paths.
    """

    mode = "docker"

    def run(self, *, image, command, cwd, env=None, timeout, workdir="/workspace", name_prefix="sc_tool", base_env=None):
        # base_env is a NATIVE-only concern: the container already starts from a
        # clean image env and receives ONLY the explicit -e ``env`` keys, so the
        # docker path is inherently scrubbed. Accepted for interface parity.
        if not shutil.which("docker"):
            return _result(
                False, "", f"Docker not found in PATH; this tool runs in the {image} container "
                "(or set SIM_ENGINE=native to run the toolchain directly).", command,
            )
        from src.tools.run_docker import run_docker_command

        name = f"{name_prefix}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        res = run_docker_command(
            command=command, image=image, cwd=workdir, workspace_path=cwd,
            timeout=timeout, env=env, name=name,
        )
        res.setdefault("timed_out", False)
        return res


class NativeToolEngine:
    """Run the command directly as a subprocess in the real workspace ``cwd``.

    Hosted / Cloud Run path: no Docker, no stage-in/out. The command must use
    cwd-relative paths (the tools build them that way). The subprocess gets its
    own process group so a timeout kills the whole tree (e.g. a runaway sim).
    """

    mode = "native"

    def run(self, *, image, command, cwd, env=None, timeout, workdir="/workspace", name_prefix="sc_tool", base_env=None):
        os.makedirs(cwd, exist_ok=True)
        # base_env, when supplied, REPLACES os.environ as the base — a caller that
        # runs untrusted user code (e.g. cocotb runs the agent's Python) passes a
        # scrubbed base so backend secrets (API keys, DB URLs) never leak into the
        # child. Default None preserves today's behavior (inherit os.environ) for
        # xls/sby, whose commands are tool invocations, not user scripts.
        base = os.environ if base_env is None else base_env
        full_env = {**base, **(env or {})}
        proc = None
        try:
            proc = subprocess.Popen(
                ["bash", "-c", command],
                cwd=cwd,
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,  # own process group for clean timeout-kill
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            rc = proc.returncode
            return _result(rc == 0, stdout, stderr, command, timed_out=False)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            return _result(False, stdout, stderr, command, timed_out=True)
        except FileNotFoundError as exc:
            return _result(False, "", f"Native tool not found: {exc}", command)
        except Exception as exc:  # noqa: BLE001
            return _result(False, "", f"Native execution error: {exc}", command)
        finally:
            if proc and proc.poll() is None:
                _kill_group(proc)


def _kill_group(proc) -> None:
    if not proc:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Factory — chosen once by settings (cached).
# ---------------------------------------------------------------------------

_ENGINE: Optional[ToolEngine] = None


def get_tool_engine() -> ToolEngine:
    """Return the process-wide tool engine selected by ``SIM_ENGINE``.

    ``docker`` (local default) → :class:`DockerToolEngine`;
    ``native`` (hosted default) → :class:`NativeToolEngine`.
    """
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    from src.platform_engines.settings import get_settings

    _ENGINE = NativeToolEngine() if get_settings().sim_engine == "native" else DockerToolEngine()
    return _ENGINE


def set_tool_engine(engine: Optional[ToolEngine]) -> None:
    """Override the process-wide tool engine (tests / explicit wiring)."""
    global _ENGINE
    _ENGINE = engine
