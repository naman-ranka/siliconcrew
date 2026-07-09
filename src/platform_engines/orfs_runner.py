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
from typing import Callable, List, Optional, Protocol

# The run contract + the remote client live in the stdlib-only shareable package
# src.orfs_client (so the Phase 1 branch can import them without this backend).
# Re-exported here for backward compatibility — existing call sites keep working.
from src.orfs_client import (  # noqa: F401  (re-exported)
    JobExecution,
    OrfsRequest,
    OrfsResult,
    OrfsRunner,
    RemoteOrfsRunner,
)


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
# (JobExecution is defined in src.orfs_client and re-exported above.)
# ---------------------------------------------------------------------------


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
        stage_in: Callable[[str, str], str],
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
        # The deterministic run_handle (when the manager set one) keys the
        # staged objects so any instance can reconstruct the prefix later;
        # stage_in mints a unique key only when no handle was provided.
        handle = self._stage_in(request.run_dir, request.run_handle)
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

        try:
            self._stage_out(request.run_dir, handle)
        except Exception as exc:
            stderr = execution.stderr or ""
            stage_out_note = f"Cloud Run Job artifact stage-out failed: {exc}"
            return OrfsResult(
                success=False,
                stdout=execution.stdout,
                stderr=f"{stderr}\n{stage_out_note}" if stderr else stage_out_note,
                command=request.command,
                exit_code=execution.exit_code,
                backend=self.backend,
            )

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
            if ":" in vol:
                parts = vol.rsplit(":", 1)
                host = parts[0]
                container = parts[1]
            else:
                host = vol
                container = ""
            try:
                rel = os.path.relpath(host, request.run_dir)
            except ValueError:
                rel = os.path.basename(host)
            if not rel.startswith(".."):
                pairs.append((rel, container))
        return pairs


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
