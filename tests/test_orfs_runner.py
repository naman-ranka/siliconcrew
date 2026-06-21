"""OrfsRunner contract + local/cloud parity (Phase 2, slice 2).

Proves the two backends are interchangeable behind one contract: the same
``OrfsRequest`` produces an equivalent ``OrfsResult`` whether it runs through the
local Docker shell-out or a Cloud Run Job. Uses fakes only — no Docker, no GCP.

The real end-to-end ORFS run (6.5 GB image, minutes, memory-heavy) is gated
behind ``RUN_REAL_ORFS=1`` so per-PR CI stays fast; it runs nightly inside the
EDA image.
"""
import os

import pytest

from src.platform_engines.orfs_runner import (
    CloudJobOrfsRunner,
    JobExecution,
    LocalDockerOrfsRunner,
    OrfsRequest,
    OrfsResult,
)


# ---- Local backend ---------------------------------------------------------


def test_local_runner_maps_docker_result_and_passes_args():
    calls = {}

    def fake_docker(command, image, cwd, workspace_path, volumes, timeout):
        calls.update(
            command=command, image=image, cwd=cwd,
            workspace_path=workspace_path, volumes=volumes, timeout=timeout,
        )
        return {"success": True, "stdout": "ok", "stderr": "", "command": "docker run ..."}

    runner = LocalDockerOrfsRunner(image="openroad/orfs:pinned", run_docker=fake_docker)
    req = OrfsRequest(
        run_dir="/runs/synth_0001",
        command="make -B DESIGN_CONFIG=/workspace/config.mk",
        volumes=["/runs/synth_0001/orfs_results:/OpenROAD-flow-scripts/flow/results"],
        timeout=1800,
    )
    result = runner.run(req)

    assert isinstance(result, OrfsResult)
    assert result.success and result.backend == "local_docker"
    assert result.stdout == "ok" and result.exit_code == 0
    # The runner forwards every field to run_docker_command unchanged.
    assert calls["workspace_path"] == "/runs/synth_0001"
    assert calls["image"] == "openroad/orfs:pinned"
    assert calls["timeout"] == 1800
    assert calls["volumes"] == req.volumes
    assert calls["command"] == req.command


def test_local_runner_maps_failure():
    def fake_docker(**_):
        return {"success": False, "stdout": "", "stderr": "boom", "command": "docker run ..."}

    runner = LocalDockerOrfsRunner(run_docker=fake_docker)
    result = runner.run(OrfsRequest(run_dir="/r", command="make"))
    assert not result.success and result.exit_code == 1 and result.stderr == "boom"


# ---- Cloud backend ---------------------------------------------------------


class FakeJobClient:
    def __init__(self, execution: JobExecution):
        self.execution = execution
        self.calls = []

    def execute(self, job, env, args, timeout):
        self.calls.append({"job": job, "env": env, "args": args, "timeout": timeout})
        return self.execution


def _staged_runner(execution: JobExecution):
    staged = {"in": [], "out": []}

    def stage_in(run_dir):
        staged["in"].append(run_dir)
        return f"handle::{os.path.basename(run_dir)}"

    def stage_out(run_dir, handle):
        staged["out"].append((run_dir, handle))

    client = FakeJobClient(execution)
    runner = CloudJobOrfsRunner(
        job_client=client, stage_in=stage_in, stage_out=stage_out,
        job="siliconcrew-orfs", image="us-docker.pkg.dev/p/r/orfs@sha256:abc",
    )
    return runner, client, staged


def test_cloud_runner_stages_in_executes_and_stages_out_on_success():
    runner, client, staged = _staged_runner(
        JobExecution(succeeded=True, exit_code=0, stdout="done", stderr="")
    )
    req = OrfsRequest(
        run_dir="/runs/synth_0007",
        command="make -B DESIGN_CONFIG=/workspace/config.mk",
        volumes=["/runs/synth_0007/orfs_results:/OpenROAD-flow-scripts/flow/results",
                 "/runs/synth_0007/orfs_logs:/OpenROAD-flow-scripts/flow/logs"],
        timeout=1200,
    )
    result = runner.run(req)

    assert result.success and result.backend == "cloud_job" and result.stdout == "done"
    assert staged["in"] == ["/runs/synth_0007"]
    assert staged["out"] == [("/runs/synth_0007", "handle::synth_0007")]
    # Job invoked with the staged handle, command, and derived result subdirs.
    env = client.calls[0]["env"]
    assert env["ORFS_RUN_HANDLE"] == "handle::synth_0007"
    assert env["ORFS_COMMAND"] == req.command
    assert env["ORFS_IMAGE"].startswith("us-docker.pkg.dev")
    assert set(env["ORFS_RESULT_SUBDIRS"].split(",")) == {"orfs_results", "orfs_logs"}
    # The Job entrypoint needs the full rundir-rel::container mapping to copy
    # ORFS outputs back to the right run-dir-relative subdirs.
    vmap = dict(p.split("::") for p in env["ORFS_VOLUME_MAP"].split(";"))
    assert vmap["orfs_results"] == "/OpenROAD-flow-scripts/flow/results"
    assert vmap["orfs_logs"] == "/OpenROAD-flow-scripts/flow/logs"


def test_cloud_runner_skips_stage_out_on_failure():
    runner, _client, staged = _staged_runner(
        JobExecution(succeeded=False, exit_code=2, stdout="", stderr="route failed")
    )
    result = runner.run(OrfsRequest(run_dir="/runs/synth_0008", command="make", volumes=[]))
    assert not result.success and result.exit_code == 2
    assert staged["in"] == ["/runs/synth_0008"]
    assert staged["out"] == []  # no artifacts pulled back on failure


def test_cloud_runner_surfaces_submission_error_in_envelope():
    class Boom:
        def execute(self, **_):
            raise RuntimeError("quota exceeded")

    runner = CloudJobOrfsRunner(
        job_client=Boom(), stage_in=lambda d: "h", stage_out=lambda d, h: None,
    )
    result = runner.run(OrfsRequest(run_dir="/r", command="make"))
    assert not result.success and result.exit_code is None
    assert "quota exceeded" in result.stderr


# ---- Parity ----------------------------------------------------------------


def test_backends_are_interchangeable_for_equivalent_request():
    """Same request → equivalent OrfsResult across backends (the swap guarantee)."""
    req = OrfsRequest(run_dir="/runs/synth_0009", command="make", volumes=[], timeout=600)

    local = LocalDockerOrfsRunner(
        run_docker=lambda **_: {"success": True, "stdout": "X", "stderr": "", "command": "c"}
    )
    cloud, _c, _s = _staged_runner(JobExecution(succeeded=True, exit_code=0, stdout="X", stderr=""))

    lr, cr = local.run(req), cloud.run(req)
    assert lr.success == cr.success == True
    assert lr.stdout == cr.stdout == "X"
    # They differ only in which backend ran — exactly the seam's intent.
    assert lr.backend != cr.backend


# ---- Heavy / nightly (owner) ----------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_ORFS") != "1",
    reason="real ORFS run is heavy/nightly; set RUN_REAL_ORFS=1 inside the EDA image",
)
def test_local_runner_real_orfs(tmp_path):  # pragma: no cover - nightly only
    """Smoke a real ORFS invocation through the local runner (needs Docker + image)."""
    from src.platform_engines.orfs_runner import LocalDockerOrfsRunner

    runner = LocalDockerOrfsRunner(image=os.environ.get("ORFS_IMAGE", "openroad/orfs:latest"))
    result = runner.run(OrfsRequest(run_dir=str(tmp_path), command="echo orfs-alive", timeout=120))
    assert result.success and "orfs-alive" in result.stdout
