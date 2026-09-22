import json
import re
import socket
import subprocess
import os
import sys
import uuid

# When running inside a container (DooD mode), sibling containers (ORFS, sby,
# python-analysis) are started by the HOST daemon, so their -v sources must be
# host paths. HOST_WORKSPACE is the host-side path of our /workspace bind mount.
# An absolute value is used as given. A relative one (docker-compose's old
# `./workspace` default) means nothing to the daemon, so, like an unset value
# inside a container, it is resolved by asking the daemon for our own mount.
_HOST_WORKSPACE = os.environ.get("HOST_WORKSPACE")
_CONTAINER_WORKSPACE_ALIASES = ("/workspace", "/app/workspace")
_discovered_host_workspace = None  # cached only once found; failures are retried


class DoodWorkspaceError(RuntimeError):
    """In a container, and the host path of /workspace is not known."""


def _is_absolute_host_path(path):
    # The host may be Windows (Docker Desktop) while we run on Linux, so
    # os.path.isabs() is not enough: accept C:\..., C:/... and UNC paths too.
    return (path.startswith("/") or path.startswith("\\\\")
            or re.match(r"^[A-Za-z]:[\\/]", path) is not None)


def _discover_host_workspace():
    """Host-side source of this container's /workspace mount, or "" if unknown.

    Docker sets the container hostname to its short id, which `docker inspect`
    accepts. Outside a container, or without a socket, this fails quietly."""
    try:
        out = subprocess.run(
            ["docker", "inspect", socket.gethostname(), "--format", "{{json .Mounts}}"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return ""
        for mount in json.loads(out.stdout) or []:
            if mount.get("Type") == "bind" and mount.get("Destination") in _CONTAINER_WORKSPACE_ALIASES:
                return mount.get("Source") or ""
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return ""


def _host_workspace():
    """The host path to rewrite /workspace to, or None when not in DooD mode.

    Raises DoodWorkspaceError inside a container when the path can't be found:
    passing `/workspace` through untranslated makes the daemon mount an empty
    host directory, and ORFS then fails with an unrelated-looking error."""
    global _discovered_host_workspace
    configured = _HOST_WORKSPACE
    if configured and _is_absolute_host_path(configured):
        return configured
    if not configured and not os.path.exists("/.dockerenv"):
        return None  # native self-host: paths are already host paths
    if not _discovered_host_workspace:
        _discovered_host_workspace = _discover_host_workspace() or None
    if _discovered_host_workspace:
        return _discovered_host_workspace
    what = (f"HOST_WORKSPACE={configured!r} is relative, which the host Docker daemon "
            "cannot mount," if configured else "HOST_WORKSPACE is not set,")
    raise DoodWorkspaceError(
        f"{what} and the host path of /workspace could not be read from "
        "`docker inspect` (is the Docker socket mounted, and the hostname the "
        "container id?). Set HOST_WORKSPACE to the absolute host path of the "
        "workspace directory (start.sh does this)."
    )


def _translate_dood_path(path):
    """Map /workspace paths from this container to the host bind mount path."""
    if not path:
        return path

    normalized = path.replace("\\", "/")
    for alias in _CONTAINER_WORKSPACE_ALIASES:
        prefix = alias + "/"
        if normalized != alias and not normalized.startswith(prefix):
            continue
        host_workspace = _host_workspace()
        if not host_workspace:
            return path
        if normalized == alias:
            return host_workspace
        suffix = normalized[len(prefix):]
        if ":" in host_workspace or "\\" in host_workspace:
            return host_workspace.rstrip("\\/") + "\\" + suffix.replace("/", "\\")
        return host_workspace.rstrip("/") + "/" + suffix
    return path


def _translate_dood_volume(volume):
    if not volume:
        return volume

    parts = volume.split(":")
    if len(parts) < 2:
        return volume

    host_path = _translate_dood_path(parts[0])
    return ":".join([host_path] + parts[1:])


def run_docker_command(command, image="openroad/orfs:latest", cwd="/OpenROAD-flow-scripts/flow", workspace_path=None, volumes=None, timeout=3600, env=None, name=None):
    """
    Executes a command inside the OpenROAD Docker container.

    Args:
        command (str or list): The command to run inside the container.
        image (str): The Docker image to use.
        cwd (str): Working directory inside the container.
        workspace_path (str): Absolute path to the local workspace directory.
                              If None, defaults to ../../workspace relative to this file.
        volumes (list): Optional list of volume mappings ["host_path:container_path"].
        timeout (int): Timeout in seconds (default 3600s).
        env (dict): Optional environment variables passed into the container (-e).
        name (str): Optional container name. When given, a timeout hard-kills the
            named container (``docker kill``) so a non-terminating run cannot
            orphan a container after the CLI is killed. Defaults to None
            (today's behavior — unchanged for existing callers).

    Returns:
        dict: {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "command": str,
            "timed_out": bool,
        }
    """

    # Resolve workspace path
    if workspace_path is None:
        # Assuming this file is in src/tools/
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        workspace_path = os.path.join(base_path, "workspace")

    # Ensure workspace exists
    if not os.path.exists(workspace_path):
        os.makedirs(workspace_path)

    # Convert command list to string if necessary
    if isinstance(command, list):
        command = " ".join(command)

    # In DooD mode, translate container paths (/workspace/...) to host paths
    # so the sibling ORFS container mounts the correct host directory.
    try:
        workspace_path = _translate_dood_path(workspace_path)
        if volumes:
            volumes = [_translate_dood_volume(v) for v in volumes]
    except DoodWorkspaceError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Error: {e}",
            "command": "docker run",
            "timed_out": False,
        }

    # Construct Docker command
    # We use --rm to clean up the container after exit
    # We mount the workspace to /workspace
    docker_cmd = ["docker", "run", "--rm"]
    if name:
        docker_cmd += ["--name", name]
    docker_cmd += ["-v", f"{workspace_path}:/workspace"]

    # Add custom volumes
    if volumes:
        for vol in volumes:
            docker_cmd.extend(["-v", vol])

    # Pass-through environment (e.g. cocotb's SC_* runner vars).
    for key, value in (env or {}).items():
        docker_cmd.extend(["-e", f"{key}={value}"])

    docker_cmd.extend([
        "-w", cwd,
        image,
        "bash", "-c", command
    ])

    proc = None
    try:
        # Run the command
        proc = subprocess.Popen(
            docker_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)

        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "command": " ".join(docker_cmd),
            "timed_out": False,
        }

    except subprocess.TimeoutExpired:
        # Killing the docker CLI alone can orphan the container; when a name was
        # supplied, hard-kill the container too.
        if name:
            subprocess.run(["docker", "kill", name], capture_output=True, text=True)
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: Docker command timed out.",
            "command": " ".join(docker_cmd),
            "timed_out": True,
        }
    except Exception as e:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Docker Execution Error: {str(e)}",
            "command": " ".join(docker_cmd),
            "timed_out": False,
        }
    finally:
        if proc and proc.poll() is None:
            proc.kill()
