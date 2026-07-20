"""GcpCloudRunJobClient: submit -> poll/backoff -> terminal (Phase 2 I6).

No GCP, no spend: a fake submit_fn returns a fake long-running operation whose
done()/result() we control. Verifies success, failure, the backoff poll loop,
timeout, and that env/args overrides reach the submission.
"""
import os

import pytest

from src.platform_engines.gcp_clients import GcpCloudRunJobClient
from src.platform_engines.orfs_runner import CloudJobOrfsRunner, JobExecution, OrfsRequest


class FakeExecution:
    def __init__(self, succeeded_count=1, failed_count=0, name="exec-123"):
        self.succeeded_count = succeeded_count
        self.failed_count = failed_count
        self.name = name


class FakeOperation:
    """Becomes done() after ``ticks`` polls, then result() returns execution."""

    def __init__(self, execution, ticks=0, raise_on_result=None):
        self._execution = execution
        self._ticks = ticks
        self._raise = raise_on_result

    def done(self):
        if self._ticks <= 0:
            return True
        self._ticks -= 1
        return False

    def result(self):
        if self._raise:
            raise self._raise
        return self._execution


def _client(submit_fn, **kw):
    # Instant sleep so backoff doesn't slow the test.
    return GcpCloudRunJobClient("proj", "us-central1", submit_fn=submit_fn,
                                logging_client=_NoLogs(), sleep=lambda s: None, **kw)


class _NoLogs:
    def list_entries(self, **_):
        return []


def test_success_returns_succeeded_execution():
    captured = {}

    def submit(name, env, args):
        captured.update(name=name, env=env, args=args)
        return FakeOperation(FakeExecution(succeeded_count=1))

    res = _client(submit).execute("siliconcrew-orfs", {"ORFS_COMMAND": "make"}, [], timeout=60)
    assert isinstance(res, JobExecution)
    assert res.succeeded and res.exit_code == 0
    # Overrides reached the submission, against the fully-qualified job name.
    assert captured["name"] == "projects/proj/locations/us-central1/jobs/siliconcrew-orfs"
    assert captured["env"]["ORFS_COMMAND"] == "make"


def test_failure_maps_to_unsucceeded():
    def submit(name, env, args):
        return FakeOperation(FakeExecution(succeeded_count=0, failed_count=1))

    res = _client(submit).execute("j", {}, [], timeout=60)
    assert not res.succeeded and res.exit_code == 1
    assert "failed task" in res.stderr


def test_polls_until_done_with_backoff():
    slept = []

    def submit(name, env, args):
        return FakeOperation(FakeExecution(), ticks=3)  # not done for 3 polls

    client = GcpCloudRunJobClient("p", "r", submit_fn=submit, logging_client=_NoLogs(),
                                  sleep=lambda s: slept.append(s), poll_initial=1.0, poll_max=4.0)
    res = client.execute("j", {}, [], timeout=600)
    assert res.succeeded
    # Exponential backoff capped at poll_max: 1, 2, 4.
    assert slept == [1.0, 2.0, 4.0]


def test_timeout_returns_unsucceeded_without_result():
    # An operation that never completes; a fake clock jumps past the deadline.
    times = iter([0, 0, 100, 200, 300])

    def submit(name, env, args):
        return FakeOperation(FakeExecution(), ticks=10_000)

    client = GcpCloudRunJobClient("p", "r", submit_fn=submit, logging_client=_NoLogs(),
                                  sleep=lambda s: None, clock=lambda: next(times))
    res = client.execute("j", {}, [], timeout=50)
    assert not res.succeeded and res.exit_code is None and "timeout" in res.stderr.lower()


def test_result_exception_is_handled():
    def submit(name, env, args):
        return FakeOperation(FakeExecution(), raise_on_result=RuntimeError("boom"))

    res = _client(submit).execute("j", {}, [], timeout=60)
    assert not res.succeeded and "boom" in res.stderr


def test_end_to_end_behind_cloud_job_orfs_runner(tmp_path):
    """The client plugs into CloudJobOrfsRunner with stage in/out fakes."""
    staged = {"in": [], "out": []}

    def submit(name, env, args):
        # The runner passes the staged handle + command through env.
        assert env["ORFS_RUN_HANDLE"].startswith("handle::")
        return FakeOperation(FakeExecution(succeeded_count=1))

    runner = CloudJobOrfsRunner(
        job_client=_client(submit),
        stage_in=lambda d, h="": (staged["in"].append(d) or f"handle::{os.path.basename(d)}"),
        stage_out=lambda d, h: staged["out"].append((d, h)),
        job="siliconcrew-orfs",
    )
    res = runner.run(OrfsRequest(run_dir=str(tmp_path / "synth_0001"), command="make", volumes=[]))
    assert res.success and res.backend == "cloud_job"
    assert staged["in"] and staged["out"]  # staged in, ran, staged artifacts back


@pytest.mark.requires_services
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("RUN_REAL_CLOUD_RUN") != "1",
    reason="real Cloud Run Job submission costs money; set RUN_REAL_CLOUD_RUN=1 + GCP creds",
)
def test_real_cloud_run_submission():  # pragma: no cover - manual/deploy-time only
    project = os.environ["GCP_PROJECT"]
    client = GcpCloudRunJobClient(project, os.environ.get("GCP_REGION", "us-central1"))
    res = client.execute(os.environ.get("ORFS_CLOUD_RUN_JOB", "siliconcrew-orfs"),
                         {"ORFS_COMMAND": "echo hi"}, [], timeout=300)
    assert isinstance(res, JobExecution)
