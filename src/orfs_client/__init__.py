"""siliconcrew-orfs-client — the shareable ORFS runner contract (stdlib only).

This package is the merge-safe home for the surface BOTH the Phase 2 backend and
the Phase 1 frontend/action-API branch can depend on to drive a real synthesis
job against a standalone ORFS service, WITHOUT importing the rest of the
backend. It has **no** third-party dependencies.

Exports:
  * ``OrfsRequest`` / ``OrfsResult`` — the run contract (mirrors the local
    ``run_docker_command`` return shape).
  * ``OrfsRunner`` — the Protocol (``.run(OrfsRequest) -> OrfsResult``).
  * ``JobExecution`` — a single cloud job's terminal state.
  * ``RemoteOrfsRunner`` — an ``OrfsRunner`` that speaks the HTTP wire contract
    in ``deploy/ORFS_SERVICE.md`` (tar run dir → POST → poll → untar artifacts).
  * ``tar_dir_b64`` / ``untar_b64_into`` — path-traversal-safe tar helpers used
    by both client and service.

``src.platform_engines.orfs_runner`` re-exports these names for backward
compatibility, so existing imports keep working.
"""
from __future__ import annotations

import base64
import io
import os
import tarfile
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Run contract
# ---------------------------------------------------------------------------


@dataclass
class OrfsRequest:
    """One ORFS invocation against an isolated, self-contained run directory.

    ``run_dir`` already contains everything ORFS needs (``config.mk``, ``inputs/``,
    ``constraints.sdc``) — it is a pure function of (manifest subset + toolchain).
    ``command`` is the make command(s) to run inside the ORFS container. ``volumes``
    are extra ``host:container`` mounts the local backend uses for results/logs/
    reports; the cloud/remote backends stage those subpaths to/from storage.
    """

    run_dir: str
    command: str
    volumes: List[str] = field(default_factory=list)
    timeout: int = 3600
    image: Optional[str] = None  # None → runner's configured image (digest-pinned in cloud)
    cwd: str = "/OpenROAD-flow-scripts/flow"
    workspace_mount: str = "/workspace"
    # Deterministic object-storage handle for this run ("<session_id>/<run_id>",
    # set by the dispatching manager). When non-empty the cloud runner stages
    # the run under it instead of minting a UUID, so ANY instance can later
    # reconstruct the prefix (durable meta pushes / orphan-output adoption)
    # from the run alone. Empty → runner-minted key (legacy/local; harmless).
    run_handle: str = ""


@dataclass
class OrfsResult:
    """Outcome of an ORFS run — same fields the rest of the pipeline expects."""

    success: bool
    stdout: str
    stderr: str
    command: str
    exit_code: Optional[int] = None
    backend: str = "local_docker"


class OrfsRunner(Protocol):
    def run(self, request: OrfsRequest) -> OrfsResult: ...


@dataclass
class JobExecution:
    """Result of a single Cloud Run Job execution."""

    succeeded: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


# ---------------------------------------------------------------------------
# tar helpers (path-traversal-safe extraction)
# ---------------------------------------------------------------------------


def tar_dir_b64(local_dir: str, subdirs: Optional[List[str]] = None) -> str:
    """Gzip-tar a directory tree (or just ``subdirs``) → base64 ascii string."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        names = subdirs if subdirs else (sorted(os.listdir(local_dir)) if os.path.isdir(local_dir) else [])
        for name in names:
            path = os.path.join(local_dir, name)
            if os.path.exists(path):
                tar.add(path, arcname=name)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def untar_b64_into(data_b64: str, local_dir: str) -> None:
    """Extract a base64 gzip tar into ``local_dir``, refusing path traversal."""
    os.makedirs(local_dir, exist_ok=True)
    raw = base64.b64decode(data_b64)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        dest_real = os.path.realpath(local_dir)
        for m in tar.getmembers():
            target = os.path.realpath(os.path.join(local_dir, m.name))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise ValueError(f"Refusing path-traversal tar member: {m.name}")
        tar.extractall(local_dir)


# ---------------------------------------------------------------------------
# Default HTTP transport + the remote runner client
# ---------------------------------------------------------------------------


class _UrllibHttp:
    """Default JSON-over-HTTP transport (stdlib only)."""

    def __init__(self, timeout: float = 60.0):
        self._timeout = timeout

    def __call__(self, method: str, url: str, json_body: Optional[dict], token: str):
        import json as _json
        import urllib.error
        import urllib.request

        data = _json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                return resp.status, (_json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            try:
                return e.code, _json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {}


class RemoteOrfsRunner:
    """OrfsRunner that delegates to a standalone ORFS HTTP service.

    ``run`` tars the (self-contained) run dir, submits it, polls with backoff,
    and untars the returned artifacts back into the same run dir — so the rest
    of the pipeline sees the normal on-disk layout, exactly like the local and
    cloud backends. ``http`` is injectable (loopback in tests).
    """

    backend = "remote"

    def __init__(
        self,
        service_url: str,
        token: str = "",
        http: Optional[Callable] = None,
        poll_initial: float = 1.0,
        poll_max: float = 10.0,
        clock: Callable[[], float] = None,
        sleep: Callable[[float], None] = None,
    ):
        import time as _t

        self._url = service_url.rstrip("/")
        self._token = token
        self._http = http or _UrllibHttp()
        self._poll_initial = poll_initial
        self._poll_max = poll_max
        self._clock = clock or _t.time
        self._sleep = sleep or _t.sleep

    def run(self, request: OrfsRequest) -> OrfsResult:
        # Volumes as run-dir-relative specs the service rebuilds against its host.
        volumes = []
        for vol in request.volumes:
            if ":" in vol:
                parts = vol.rsplit(":", 1)
                host = parts[0]
                container = parts[1]
            else:
                host = vol
                container = ""
            rel = os.path.relpath(host, request.run_dir)
            if not rel.startswith(".."):
                volumes.append(f"{rel}:{container}" if container else rel)

        payload = {
            "command": request.command,
            "volumes": volumes,
            "timeout": request.timeout,
            "inputs_tar_b64": tar_dir_b64(request.run_dir),
        }
        try:
            status, body = self._http("POST", f"{self._url}/v1/jobs", payload, self._token)
        except Exception as exc:  # network / transport failure
            return OrfsResult(False, "", f"Remote ORFS submit failed: {exc}", request.command, None, self.backend)
        if status != 200:
            return OrfsResult(False, "", f"Remote ORFS submit HTTP {status}: {body}", request.command, None, self.backend)

        job_id = body["job_id"]
        deadline = self._clock() + request.timeout + 120
        delay = self._poll_initial
        st: dict = {}
        while True:
            _s, st = self._http("GET", f"{self._url}/v1/jobs/{job_id}", None, self._token)
            if st.get("status") in ("succeeded", "failed"):
                break
            if self._clock() >= deadline:
                return OrfsResult(False, "", "Remote ORFS job timed out.", request.command, None, self.backend)
            self._sleep(delay)
            delay = min(delay * 2, self._poll_max)

        succeeded = st.get("status") == "succeeded"
        if succeeded:
            a_status, art = self._http("GET", f"{self._url}/v1/jobs/{job_id}/artifacts", None, self._token)
            if a_status == 200 and art.get("artifacts_tar_b64"):
                untar_b64_into(art["artifacts_tar_b64"], request.run_dir)

        return OrfsResult(
            success=succeeded,
            stdout=st.get("stdout", "") or "",
            stderr=st.get("stderr", "") or "",
            command=request.command,
            exit_code=st.get("exit_code"),
            backend=self.backend,
        )


__all__ = [
    "OrfsRequest",
    "OrfsResult",
    "OrfsRunner",
    "JobExecution",
    "RemoteOrfsRunner",
    "tar_dir_b64",
    "untar_b64_into",
]
