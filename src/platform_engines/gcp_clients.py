"""Concrete GCP clients for the cloud engines (Phase 2 I6).

Currently: :class:`GcpCloudRunJobClient`, the missing blocker behind
:class:`~src.platform_engines.orfs_runner.CloudJobOrfsRunner`. It submits an
execution of the **pre-deployed** Cloud Run Job (created by Terraform), polls
the long-running operation with exponential backoff until terminal or timeout,
captures the execution's logs (best effort), and returns a
:class:`~src.platform_engines.orfs_runner.JobExecution`.

Design for testability + deploy-readiness:
  * the google-cloud SDK is imported lazily, so importing this module never
    requires it (self-host / CI stay clean);
  * the actual submission is a small injectable seam (``submit_fn``) and the
    clock/sleep are injectable, so the whole poll/backoff/terminal logic is
    unit-tested against a fake operation with no GCP and no real spend;
  * a real submission is gated behind ``RUN_REAL_CLOUD_RUN=1`` in tests.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, List, Optional

from src.platform_engines.orfs_runner import JobExecution


class GcpCloudRunJobClient:
    """Submit + await one execution of a pre-deployed Cloud Run Job."""

    def __init__(
        self,
        project: str,
        region: str,
        *,
        submit_fn: Optional[Callable[[str, dict, List[str]], Any]] = None,
        logging_client: Any = None,
        poll_initial: float = 2.0,
        poll_max: float = 30.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._project = project
        self._region = region
        self._submit_fn = submit_fn  # injectable; default uses google-cloud-run
        self._logging_client = logging_client
        self._poll_initial = poll_initial
        self._poll_max = poll_max
        self._clock = clock
        self._sleep = sleep
        self._jobs_client = None

    def _job_name(self, job: str) -> str:
        return f"projects/{self._project}/locations/{self._region}/jobs/{job}"

    def execute(self, job: str, env: dict, args: List[str], timeout: int) -> JobExecution:
        """Run the Job once with env/arg overrides; block (bounded) for the result."""
        name = self._job_name(job)
        submit = self._submit_fn or self._default_submit
        operation = submit(name, env, args)

        # Poll the long-running operation with exponential backoff.
        deadline = self._clock() + max(1, int(timeout))
        delay = self._poll_initial
        while not _op_done(operation):
            if self._clock() >= deadline:
                return JobExecution(
                    succeeded=False,
                    exit_code=None,
                    stdout="",
                    stderr=f"Cloud Run Job '{job}' did not finish within {timeout}s (timeout).",
                )
            self._sleep(delay)
            delay = min(delay * 2, self._poll_max)

        try:
            execution = operation.result()
        except Exception as exc:  # operation finished in error
            return JobExecution(False, exit_code=1, stdout="", stderr=f"Cloud Run Job failed: {exc}")

        succeeded = _execution_succeeded(execution)
        logs = self._capture_logs(name, execution)
        return JobExecution(
            succeeded=succeeded,
            exit_code=0 if succeeded else 1,
            stdout=logs,
            stderr="" if succeeded else _failure_reason(execution),
        )

    # -- real SDK paths (lazy; never hit in unit tests) ----------------------

    def _default_submit(self, name: str, env: dict, args: List[str]):
        from google.cloud import run_v2  # lazy

        if self._jobs_client is None:
            self._jobs_client = run_v2.JobsClient()

        container_override = run_v2.RunJobRequest.Overrides.ContainerOverride(
            env=[run_v2.EnvVar(name=k, value=str(v)) for k, v in env.items()],
            args=list(args),
        )
        request = run_v2.RunJobRequest(
            name=name,
            overrides=run_v2.RunJobRequest.Overrides(container_overrides=[container_override]),
        )
        return self._jobs_client.run_job(request=request)

    def _capture_logs(self, name: str, execution: Any) -> str:
        """Best-effort: pull the execution's stdout/stderr from Cloud Logging."""
        client = self._logging_client
        try:
            if client is None:
                from google.cloud import logging as gcp_logging  # lazy

                client = gcp_logging.Client(project=self._project)
            exec_name = getattr(execution, "name", "") or name
            exec_id = exec_name.rsplit("/", 1)[-1]
            filt = (
                'resource.type="cloud_run_job" '
                f'labels."run.googleapis.com/execution_name"="{exec_id}"'
            )
            entries = client.list_entries(filter_=filt, order_by="timestamp asc", max_results=500)
            return "\n".join(str(getattr(e, "payload", "")) for e in entries)
        except Exception:
            return ""  # logs are diagnostic, not load-bearing


# ---------------------------------------------------------------------------
# Small adapters over the SDK's duck-typed objects (kept module-level so fakes
# in tests only need to mimic the tiny surface used here).
# ---------------------------------------------------------------------------


def _op_done(operation: Any) -> bool:
    done = getattr(operation, "done", None)
    return bool(done()) if callable(done) else bool(done)


def _execution_succeeded(execution: Any) -> bool:
    # Cloud Run v2 Execution exposes succeeded_count / failed_count / task_count.
    succeeded = getattr(execution, "succeeded_count", None)
    failed = getattr(execution, "failed_count", None)
    if succeeded is not None:
        return int(succeeded) >= 1 and int(failed or 0) == 0
    # Fallback: an explicit boolean if a fake/other shape provides it.
    return bool(getattr(execution, "succeeded", False))


def _failure_reason(execution: Any) -> str:
    failed = getattr(execution, "failed_count", None)
    if failed:
        return f"Cloud Run Job execution reported {failed} failed task(s)."
    cond = getattr(execution, "conditions", None)
    if cond:
        return "; ".join(str(getattr(c, "message", c)) for c in cond)
    return "Cloud Run Job execution did not succeed."
