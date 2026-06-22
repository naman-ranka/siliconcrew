"""OrfsRunner — the seam for *where ORFS executes*.

Today ``synthesis_manager`` shells ``docker run openroad/orfs`` via the host
Docker socket (Docker-outside-of-Docker). Sharing that socket is effectively
root on the host — unacceptable when untrusted users' designs run on a shared
box. This module puts ORFS execution behind one small interface so the run
*management* (run dirs, snapshots, staged retry, the index, report parsing) is
completely unchanged; only the execution backend swaps:

  * :class:`LocalDockerOrfsRunner` — today's behavior, refactored (self-host).
  * :class:`CloudJobOrfsRunner` — submit an isolated Cloud Run Job per run.

The contract (``OrfsRequest`` → ``OrfsResult``) mirrors the existing
``run_docker_command`` return shape so the synthesis manager maps onto it with
no behavior change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol


@dataclass
class OrfsRequest:
    """One ORFS invocation against an isolated, self-contained run directory.

    ``run_dir`` already contains everything ORFS needs (``config.mk``, ``inputs/``,
    ``constraints.sdc``) — it is a pure function of (manifest subset + toolchain).
    ``command`` is the make command(s) to run inside the ORFS container. ``volumes``
    are extra ``host:container`` mounts the local backend uses for results/logs/
    reports; the cloud backend stages those same subpaths to/from object storage.
    """

    run_dir: str
    command: str
    volumes: List[str] = field(default_factory=list)
    timeout: int = 3600
    image: Optional[str] = None  # None → runner's configured image (digest-pinned in cloud)
    cwd: str = "/OpenROAD-flow-scripts/flow"
    workspace_mount: str = "/workspace"


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


# ---------------------------------------------------------------------------
# Local backend — refactor of the run_docker path (no behavior change).
# ---------------------------------------------------------------------------


class LocalDockerOrfsRunner:
    """Runs ORFS via the host Docker daemon — exactly today's path, behind the seam.

    A thin adapter over ``src.tools.run_docker.run_docker_command`` so the local /
    self-host experience is byte-for-byte unchanged.
    """

    backend = "local_docker"

    def __init__(self, image: str = "openroad/orfs:latest", run_docker=None):
        self.image = image
        # Injectable for tests; defaults to the real docker shell-out.
        self._run_docker = run_docker

    def _docker(self):
        if self._run_docker is not None:
            return self._run_docker
        from src.tools.run_docker import run_docker_command

        return run_docker_command

    def run(self, request: OrfsRequest) -> OrfsResult:
        result = self._docker()(
            command=request.command,
            image=request.image or self.image,
            cwd=request.cwd,
            workspace_path=request.run_dir,
            volumes=list(request.volumes),
            timeout=request.timeout,
        )
        return OrfsResult(
            success=bool(result.get("success")),
            stdout=result.get("stdout", "") or "",
            stderr=result.get("stderr", "") or "",
            command=result.get("command", request.command),
            exit_code=0 if result.get("success") else 1,
            backend=self.backend,
        )


# ---------------------------------------------------------------------------
# Cloud backend — isolated Cloud Run Job per synth run.
# ---------------------------------------------------------------------------


@dataclass
class JobExecution:
    """Result of a single Cloud Run Job execution."""

    succeeded: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class CloudRunJobClient(Protocol):
    """Minimal Cloud Run Jobs surface (injectable; real impl uses google-cloud-run).

    ``execute`` submits an execution of a pre-deployed Job (the ORFS image lives
    in Artifact Registry; the Job template is created by Terraform) with a small
    set of env overrides, waits, and returns the terminal state.
    """

    def execute(self, job: str, env: dict, args: List[str], timeout: int) -> JobExecution: ...


class CloudJobOrfsRunner:
    """Submit one isolated Cloud Run Job per ORFS run — no shared Docker socket.

    Flow per run (the README's "stage in → run → stage out"):
      1. ``stage_in(run_dir)``  — tar the self-contained run dir to object storage,
         returning an opaque handle the Job can pull.
      2. ``job_client.execute(...)`` — run ORFS in an isolated sandbox; the Job
         downloads the tar, runs ``command``, and uploads results/logs/reports.
      3. ``stage_out(run_dir, handle)`` — pull the produced artifacts back into the
         local ``run_dir`` so the unchanged downstream parsers (snapshots, index,
         report extraction) see exactly the same on-disk layout as local mode.

    ``stage_in``/``stage_out`` are injected (wired to the ``WorkspaceProvider``'s
    object store in production) so this class is fully unit-testable with fakes.
    """

    backend = "cloud_job"

    def __init__(
        self,
        job_client: CloudRunJobClient,
        stage_in: Callable[[str], str],
        stage_out: Callable[[str, str], None],
        job: str = "siliconcrew-orfs",
        image: str = "openroad/orfs:latest",
    ):
        self._client = job_client
        self._stage_in = stage_in
        self._stage_out = stage_out
        self._job = job
        self._image = image

    def run(self, request: OrfsRequest) -> OrfsResult:
        # Cloud Run Jobs are isolated and parallel by default; volumes are not
        # bind mounts there. We stage the whole self-contained run dir instead.
        handle = self._stage_in(request.run_dir)
        env = {
            "ORFS_RUN_HANDLE": handle,
            "ORFS_COMMAND": request.command,
            "ORFS_TIMEOUT": str(request.timeout),
            "ORFS_IMAGE": request.image or self._image,
            # The Job entrypoint replays the same volume subpaths (results/logs/
            # reports) into the staged tree so stage_out restores them locally.
            "ORFS_RESULT_SUBDIRS": ",".join(self._result_subdirs(request)),
            # Full mapping the Job needs to copy ORFS container outputs back to
            # the run-dir-relative subdirs: "<rel>::<container_path>" per entry.
            "ORFS_VOLUME_MAP": ";".join(self._volume_map(request)),
        }
        try:
            execution = self._client.execute(
                job=self._job, env=env, args=[], timeout=request.timeout
            )
        except Exception as exc:  # surface infra failures in the same envelope
            return OrfsResult(
                success=False,
                stdout="",
                stderr=f"Cloud Run Job submission failed: {exc}",
                command=request.command,
                exit_code=None,
                backend=self.backend,
            )

        if execution.succeeded:
            # Only pull artifacts back on success; on failure the local run dir
            # keeps the config/inputs and the captured logs below for diagnosis.
            self._stage_out(request.run_dir, handle)

        return OrfsResult(
            success=execution.succeeded,
            stdout=execution.stdout,
            stderr=execution.stderr,
            command=request.command,
            exit_code=execution.exit_code,
            backend=self.backend,
        )

    @staticmethod
    def _result_subdirs(request: OrfsRequest) -> List[str]:
        """Derive the run-dir-relative output subdirs from the volume specs."""
        return [rel for rel, _container in CloudJobOrfsRunner._volume_pairs(request)]

    @staticmethod
    def _volume_map(request: OrfsRequest) -> List[str]:
        """Encode each volume as '<rundir-rel>::<container-path>' for the Job."""
        return [f"{rel}::{container}" for rel, container in CloudJobOrfsRunner._volume_pairs(request)]

    @staticmethod
    def _volume_pairs(request: OrfsRequest):
        """Yield (rundir-relative dest, ORFS container source) for each volume."""
        pairs = []
        for vol in request.volumes:
            parts = vol.split(":")
            host = parts[0]
            container = parts[1] if len(parts) > 1 else ""
            try:
                rel = os.path.relpath(host, request.run_dir)
            except ValueError:
                rel = os.path.basename(host)
            if not rel.startswith(".."):
                pairs.append((rel, container))
        return pairs


# ---------------------------------------------------------------------------
# Remote backend — call a standalone ORFS HTTP service (cross-agent reuse).
# ---------------------------------------------------------------------------
#
# This class + the OrfsRunner interface + the dataclasses above are the
# SHAREABLE surface: an external client (e.g. the Phase 1 branch) can drive a
# real synth by pointing RemoteOrfsRunner at the service URL, without importing
# the rest of this backend. The wire contract is in deploy/ORFS_SERVICE.md.


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
        import base64
        from src.platform_engines.orfs_service import tar_dir_b64, untar_b64_into

        # Volumes as run-dir-relative specs the service rebuilds against its host.
        volumes = []
        for vol in request.volumes:
            parts = vol.split(":")
            host = parts[0]
            container = parts[1] if len(parts) > 1 else ""
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


# ---------------------------------------------------------------------------
# Factory — chosen once by settings.
# ---------------------------------------------------------------------------

_RUNNER: Optional[OrfsRunner] = None


def get_orfs_runner() -> OrfsRunner:
    """Return the process-wide ORFS runner selected by platform settings.

    Local/self-host gets :class:`LocalDockerOrfsRunner` (today's behavior). The
    cloud runner is constructed lazily so importing this module never requires
    the google-cloud SDK in local mode.
    """
    global _RUNNER
    if _RUNNER is not None:
        return _RUNNER

    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if settings.orfs_engine == "remote":
        _RUNNER = RemoteOrfsRunner(settings.orfs_service_url, token=settings.orfs_service_token)
    elif settings.is_cloud_orfs:
        _RUNNER = _build_cloud_runner(settings)
    else:
        _RUNNER = LocalDockerOrfsRunner(image=settings.orfs_image)
    return _RUNNER


def set_orfs_runner(runner: Optional[OrfsRunner]) -> None:
    """Override the process-wide runner (tests / explicit wiring)."""
    global _RUNNER
    _RUNNER = runner


def _build_cloud_runner(settings) -> "CloudJobOrfsRunner":
    from src.platform_engines.workspace_provider import build_run_stager
    from src.platform_engines.gcp_clients import GcpCloudRunJobClient

    stage_in, stage_out = build_run_stager(settings)
    return CloudJobOrfsRunner(
        job_client=GcpCloudRunJobClient(
            project=settings.gcp_project, region=settings.gcp_region
        ),
        stage_in=stage_in,
        stage_out=stage_out,
        job=settings.cloud_run_job,
        image=settings.orfs_image,
    )
