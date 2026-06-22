"""Standalone ORFS service + RemoteOrfsRunner client, end to end (Phase 2 I7).

Drives the real wire contract (submit tarball -> poll -> fetch artifacts) over a
loopback transport that mimics the HTTP layer (incl. bearer auth), with a mock
OrfsRunner standing in for the real ORFS exec (no Docker). Proves an external
client can run a synth through the service and get artifacts back.
"""
import os

import pytest

from src.platform_engines.orfs_runner import OrfsRequest, OrfsResult, RemoteOrfsRunner
from src.platform_engines.orfs_service import OrfsService, ServiceError


class MockRunner:
    """Stand-in for a real OrfsRunner: writes a result artifact, reports success."""

    def __init__(self, succeed=True):
        self.succeed = succeed
        self.seen = []

    def run(self, req: OrfsRequest) -> OrfsResult:
        self.seen.append(req)
        if self.succeed:
            for vol in req.volumes:
                host = vol.rsplit(":", 1)[0] if ":" in vol else vol
                os.makedirs(host, exist_ok=True)
                with open(os.path.join(host, "metrics.txt"), "w") as f:
                    f.write("area_um2=42\n")
            return OrfsResult(True, "ORFS ok", "", req.command, 0, "local_docker")
        return OrfsResult(False, "", "route failed", req.command, 1, "local_docker")


def _loopback(service: OrfsService, expected_token: str):
    """An http(method, url, json, token) transport routed to the service core."""

    def http(method, url, json_body, token):
        if expected_token and token != expected_token:
            return 401, {"error": "unauthorized"}
        path = url.split("://", 1)[-1].split("/", 1)[-1]  # drop scheme+host
        path = "/" + path if not path.startswith("/") else path
        try:
            if method == "POST" and path.endswith("/v1/jobs"):
                return 200, service.submit(json_body)
            if method == "GET" and path.endswith("/artifacts"):
                job_id = path.split("/v1/jobs/")[1].rsplit("/artifacts", 1)[0]
                return 200, service.artifacts(job_id)
            if method == "GET" and "/v1/jobs/" in path:
                job_id = path.split("/v1/jobs/")[1]
                return 200, service.status(job_id)
        except ServiceError as e:
            return e.status, {"error": e.message}
        return 404, {"error": "not found"}

    return http


def _client_run_dir(tmp_path):
    run_dir = tmp_path / "client_run"
    (run_dir / "inputs").mkdir(parents=True)
    (run_dir / "inputs" / "dut.v").write_text("module dut; endmodule\n")
    (run_dir / "config.mk").write_text("export DESIGN_NAME = dut\n")
    return run_dir


def test_remote_runner_end_to_end_success(tmp_path):
    service = OrfsService(MockRunner(succeed=True), scratch_dir=str(tmp_path / "svc"))
    runner = RemoteOrfsRunner(
        "http://orfs.local", token="secret",
        http=_loopback(service, "secret"), poll_initial=0, sleep=lambda s: None,
    )
    run_dir = _client_run_dir(tmp_path)
    req = OrfsRequest(
        run_dir=str(run_dir),
        command="make DESIGN_CONFIG=/workspace/config.mk",
        volumes=[f"{run_dir}/orfs_results:/OpenROAD-flow-scripts/flow/results"],
        timeout=120,
    )
    res = runner.run(req)

    assert res.success and res.backend == "remote" and res.exit_code == 0
    assert res.stdout == "ORFS ok"
    # Artifacts produced by the service's runner were fetched back into the
    # client's own run dir — the cross-agent real-synth round trip.
    assert (run_dir / "orfs_results" / "metrics.txt").read_text().startswith("area_um2=42")


def test_remote_runner_reports_failure(tmp_path):
    service = OrfsService(MockRunner(succeed=False), scratch_dir=str(tmp_path / "svc"))
    runner = RemoteOrfsRunner("http://x", token="", http=_loopback(service, ""),
                              poll_initial=0, sleep=lambda s: None)
    run_dir = _client_run_dir(tmp_path)
    res = runner.run(OrfsRequest(run_dir=str(run_dir), command="make", volumes=[], timeout=60))
    assert not res.success and res.exit_code == 1 and "route failed" in res.stderr


def test_bad_token_is_rejected(tmp_path):
    service = OrfsService(MockRunner(), scratch_dir=str(tmp_path / "svc"))
    runner = RemoteOrfsRunner("http://x", token="wrong", http=_loopback(service, "right"),
                              poll_initial=0, sleep=lambda s: None)
    run_dir = _client_run_dir(tmp_path)
    res = runner.run(OrfsRequest(run_dir=str(run_dir), command="make", volumes=[], timeout=60))
    assert not res.success and "401" in res.stderr


def test_service_core_submit_status_artifacts(tmp_path):
    """Drive the framework-free core directly (the wire payloads)."""
    import base64
    from src.platform_engines.orfs_service import tar_dir_b64

    service = OrfsService(MockRunner(succeed=True), scratch_dir=str(tmp_path / "svc"))
    src = tmp_path / "src"
    (src / "inputs").mkdir(parents=True)
    (src / "config.mk").write_text("x\n")

    out = service.submit({
        "command": "make",
        "volumes": ["orfs_results:/flow/results"],
        "timeout": 30,
        "inputs_tar_b64": tar_dir_b64(str(src)),
    })
    job_id = out["job_id"]
    # Poll to terminal (the runner executes on a worker thread).
    import time

    st = {"status": "queued"}
    for _ in range(200):
        st = service.status(job_id)
        if st["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert st["status"] == "succeeded"

    art = service.artifacts(job_id)
    # The artifact tarball carries the declared result subdir.
    from src.platform_engines.orfs_service import untar_b64_into

    dest = tmp_path / "fetched"
    untar_b64_into(art["artifacts_tar_b64"], str(dest))
    assert (dest / "orfs_results" / "metrics.txt").exists()


def test_service_rejects_missing_inputs(tmp_path):
    service = OrfsService(MockRunner(), scratch_dir=str(tmp_path / "svc"))
    with pytest.raises(ServiceError) as ei:
        service.submit({"command": "make"})  # no inputs_tar_b64 / object_ref
    assert ei.value.status == 400


def test_finished_jobs_are_evicted_after_ttl(tmp_path):
    """The in-memory job map is bounded: finished jobs age out + scratch is removed."""
    from src.platform_engines.orfs_service import tar_dir_b64

    clock = {"t": 1000.0}
    service = OrfsService(MockRunner(succeed=True), scratch_dir=str(tmp_path / "svc"),
                          job_ttl_seconds=60.0, clock=lambda: clock["t"])
    src = tmp_path / "src"
    (src / "inputs").mkdir(parents=True)
    (src / "config.mk").write_text("x\n")

    out = service.submit({"command": "make", "volumes": [], "timeout": 30,
                          "inputs_tar_b64": tar_dir_b64(str(src))})
    job_id = out["job_id"]
    # Drive to terminal (stamps finished_at).
    import time
    for _ in range(200):
        if service.status(job_id)["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    run_dir = service._jobs[job_id]["run_dir"]
    assert os.path.isdir(run_dir)

    # Before TTL: still present. After TTL: evicted + scratch removed.
    clock["t"] += 30
    assert service.gc_now() == 1
    clock["t"] += 61
    assert service.gc_now() == 0
    assert not os.path.exists(run_dir)
    with pytest.raises(ServiceError) as ei:
        service.status(job_id)
    assert ei.value.status == 404


def test_remote_engine_selected_by_settings(monkeypatch):
    """ORFS_ENGINE=remote wires RemoteOrfsRunner via the single factory."""
    import src.platform_engines.orfs_runner as orf
    from src.platform_engines.settings import reset_settings_cache

    monkeypatch.setenv("ORFS_ENGINE", "remote")
    monkeypatch.setenv("ORFS_SERVICE_URL", "http://orfs.local")
    monkeypatch.setenv("ORFS_SERVICE_TOKEN", "tok")
    reset_settings_cache()
    orf.set_orfs_runner(None)
    try:
        runner = orf.get_orfs_runner()
        assert isinstance(runner, RemoteOrfsRunner)
    finally:
        orf.set_orfs_runner(None)
        reset_settings_cache()
