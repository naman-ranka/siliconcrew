"""Workspace-scoped Python analysis — a BESPOKE gated subprocess.

This is deliberately NOT routed through ``ToolEngine``/``run_docker_command``:
``NativeToolEngine.run`` merges ``{**os.environ, **env}`` (it can only ADD keys,
never scrub) and ``run_docker_command`` hard-codes ``docker run`` with no
isolation flags. Both are shared by xls/sby/cocotb, so this tool builds its own
subprocess with an explicit **scrubbed** env + POSIX rlimits (native) and its own
``docker run`` with real isolation flags (docker). See plan PA1/PA2.

The script is a WORKSPACE FILE (agents ``write_file`` it first), so a run records
exactly what executed. Accident-gates are always on in both engines: 30s wall
timeout, ``cwd=workspace``, scrubbed env, ``python -I`` (native), and — where the
platform supports it — CPU/mem/file/proc rlimits (native) or container caps
(docker). Malice-isolation (``--network=none``, non-root, read-only rootfs) comes
free from Docker; native mode honestly trusts the local machine (documented).

Returns a plain dict; the wrapper JSON-encodes it. ``artifacts`` is a post-run
mtime scan of the workspace so the tool card can render "Open artifact →".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from typing import List, Optional

from src.utils.paths import is_within

# Default accident-gate ceilings (both engines).
_WALL_TIMEOUT_SEC = 30
_CPU_SECONDS = 30
_RSS_BYTES = 2 * 1024 * 1024 * 1024        # address-space cap (see _posix_rlimits note)
_FSIZE_BYTES = 256 * 1024 * 1024
_NPROC = 64
_TAIL = 16000

# Default pinned analysis image (see docker/python-analysis/Dockerfile, PA12).
DEFAULT_PYTHON_IMAGE = "siliconcrew/python-analysis:1"

# Artifact family by extension — mirrors the backend/frontend artifact kinds
# (plan Item 4/5). Anything unmapped is "file" (download-only).
_KIND_BY_EXT = {
    **{e: "image" for e in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")},
    **{e: "data" for e in (".csv", ".tsv", ".json", ".yaml", ".yml")},
    **{e: "text" for e in (".txt", ".log", ".rpt", ".md", ".out")},
    **{e: "vector" for e in (".hex", ".mem", ".coe", ".bin")},
}


def _artifact_kind(rel_path: str) -> str:
    return _KIND_BY_EXT.get(os.path.splitext(rel_path)[1].lower(), "file")


class PythonAnalysisError(Exception):
    """Raised for a caller error (containment/validation) before any execution."""


def resolve_engine(engine: Optional[str] = None) -> str:
    """Pick the engine: explicit arg > ``python_engine`` setting, with a native
    fallback when docker is requested but the docker CLI is absent."""
    if not engine:
        try:
            from src.platform_engines.settings import get_settings

            engine = getattr(get_settings(), "python_engine", "docker")
        except Exception:
            engine = "docker"
    if engine == "docker" and not shutil.which("docker"):
        return "native"
    return engine


def _scrubbed_env(workspace: str) -> dict:
    """A minimal, EXPLICIT env for the child — NEVER the backend process env
    (which holds API keys / DB URLs). This is the single most important native
    gate. ``MPLCONFIGDIR`` is a workspace dot-dir so matplotlib's cache is both
    writable and invisible to the artifact scan (dot-dirs are excluded)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": workspace,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": os.path.join(workspace, ".matplotlib"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # Windows: the interpreter itself needs a few system vars to even start.
    # These are not secrets; a planted SECRET/API key is still excluded.
    for key in ("SYSTEMROOT", "SystemRoot", "WINDIR", "PATHEXT", "TEMP", "TMP", "COMSPEC"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env


def _posix_rlimits():
    """Return a ``preexec_fn`` applying CPU/AS/FSIZE/NPROC rlimits + a new session
    (so a timeout kills the whole tree), or ``None`` on non-POSIX platforms.

    Note: Linux has no enforced RSS rlimit, so we cap RLIMIT_AS (address space).
    numpy/matplotlib reserve a lot of virtual memory at import, so the cap is set
    generously (2GB) — enough to stop a runaway allocation without false-killing a
    legitimate plot.
    """
    try:
        import resource  # POSIX-only
    except ImportError:
        return None

    def _apply():
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_SECONDS, _CPU_SECONDS))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (_RSS_BYTES, _RSS_BYTES))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_BYTES, _FSIZE_BYTES))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (_NPROC, _NPROC))
        except (ValueError, OSError):
            pass
        os.setsid()

    return _apply


def build_docker_argv(*, image: str, workspace: str, rel_script: str, args: List[str]) -> List[str]:
    """The isolated ``docker run`` argv (pure — unit-testable without Docker).

    Real isolation: no network, non-root, memory/cpu/pids caps, read-only rootfs
    with only the workspace (rw) and a small ``/tmp`` tmpfs writable. The single
    ``-v`` is routed through ``_translate_dood_volume`` for docker-outside-docker
    (PA2)."""
    from src.tools.run_docker import _translate_dood_volume

    volume = _translate_dood_volume(f"{workspace}:/workspace:rw")
    return [
        "docker", "run", "--rm",
        "--network=none",
        "--user", "1000:1000",
        "--memory", "1g", "--memory-swap", "1g",
        "--cpus", "1",
        "--pids-limit", str(_NPROC),
        "--read-only",
        "--tmpfs", "/tmp:rw,size=256m,exec",
        "-v", volume,
        "-w", "/workspace",
        "-e", "HOME=/tmp",
        "-e", "MPLBACKEND=Agg",
        "-e", "MPLCONFIGDIR=/tmp/.matplotlib",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        image,
        "python", "-I", f"/workspace/{rel_script}", *[str(a) for a in args],
    ]


def _run_argv(argv, *, cwd=None, env=None, preexec_fn=None, timeout=_WALL_TIMEOUT_SEC):
    """Run ``argv`` (no shell), capture output, enforce a wall timeout. Returns
    ``(exit_code, stdout, stderr, timed_out)``. Kills the whole process group on
    timeout where the platform supports it."""
    popen_kwargs = dict(
        cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if preexec_fn is not None:
        popen_kwargs["preexec_fn"] = preexec_fn
    elif os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    proc = None
    try:
        proc = subprocess.Popen(argv, **popen_kwargs)
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout or "", stderr or "", False
    except subprocess.TimeoutExpired:
        _kill(proc)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
        return None, stdout or "", stderr or "", True
    except FileNotFoundError as exc:
        return None, "", f"executable not found: {exc}", False
    finally:
        if proc and proc.poll() is None:
            _kill(proc)


def _kill(proc) -> None:
    if not proc:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _scan_artifacts(workspace: str, since: float, exclude: Optional[set] = None,
                    ignore: Optional[List[str]] = None):
    """Files created/modified during the run (mtime >= start), under the shared
    manifest scan policy (excludes sim_runs/synth_runs/dot-dirs/etc, PA6). The
    input script is excluded — it is what ran, not an output the run produced."""
    from src.tools.manifest import iter_workspace_files

    exclude = exclude or set()
    out = []
    for rel in iter_workspace_files(workspace, ignore=ignore or []):
        if rel in exclude:
            continue
        ap = os.path.join(workspace, rel)
        try:
            st = os.stat(ap)
        except OSError:
            continue
        # Small tolerance for filesystem mtime granularity.
        if st.st_mtime + 0.001 >= since:
            out.append({"path": rel, "kind": _artifact_kind(rel), "bytes": st.st_size})
    out.sort(key=lambda a: a["path"])
    return out


def run_python_analysis(
    workspace: str,
    script_file: str,
    args: Optional[List[str]] = None,
    *,
    engine: Optional[str] = None,
    timeout: int = _WALL_TIMEOUT_SEC,
    image: Optional[str] = None,
) -> dict:
    """Execute ``script_file`` (a workspace file) as an isolated subprocess.

    Raises ``PythonAnalysisError`` for a containment/validation failure BEFORE any
    execution. Otherwise returns a result dict:
    ``{ok, exit_code, stdout_tail, stderr_tail, duration_sec, engine, artifacts,
       timed_out}``.
    """
    args = [str(a) for a in (args or [])]
    if not script_file or not isinstance(script_file, str):
        raise PythonAnalysisError("script_file is required (a workspace-relative .py path).")

    # Containment (PA5): resolve the script INSIDE the workspace, symlink/`..`-safe
    # via realpath. The tool checks this ITSELF — enforce_file_containment only
    # auto-runs on /invoke, not on the agent/MCP paths.
    candidate = script_file if os.path.isabs(script_file) else os.path.join(workspace, script_file)
    if not is_within(workspace, candidate):
        raise PythonAnalysisError(f"script_file escapes the workspace: {script_file}")
    if not os.path.isfile(candidate):
        raise PythonAnalysisError(f"script_file not found in workspace: {script_file}")

    rel_script = os.path.relpath(candidate, workspace).replace("\\", "/")
    engine = resolve_engine(engine)
    image = image or DEFAULT_PYTHON_IMAGE

    start = time.time()
    if engine == "docker":
        argv = build_docker_argv(image=image, workspace=workspace, rel_script=rel_script, args=args)
        exit_code, stdout, stderr, timed_out = _run_argv(argv, timeout=timeout)
    else:
        engine = "native"
        argv = [sys.executable, "-I", candidate, *args]
        exit_code, stdout, stderr, timed_out = _run_argv(
            argv, cwd=workspace, env=_scrubbed_env(workspace),
            preexec_fn=_posix_rlimits(), timeout=timeout,
        )
    duration = round(time.time() - start, 3)

    return {
        "ok": (not timed_out) and exit_code == 0,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_sec": duration,
        "engine": engine,
        "stdout_tail": (stdout or "")[-_TAIL:],
        "stderr_tail": (stderr or "")[-_TAIL:],
        "artifacts": _scan_artifacts(workspace, start, exclude={rel_script}),
    }
