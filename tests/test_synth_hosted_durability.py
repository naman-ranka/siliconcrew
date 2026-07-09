"""Hosted durability (Wave 9, Item 4): any instance can finalize a run.

Covers the four legs against recording fakes (no live GCS/Cloud Run):
- ObjectStore additions: put_file stores raw objects; exists sees both tar
  blobs and raw objects (get_tree keeps its silent empty-dir behavior for
  absent blobs — exists is the explicit check).
- Deterministic run handle: the manager computes <session_id>/<run_id> (the
  run store's "orfs-runs" prefix supplies the outer segment) and passes it
  through OrfsRequest.run_handle; the cloud runner stages under it instead of
  minting a UUID.
- Progressive meta push: worker milestones persist run_meta.json to
  <handle>/meta/run_meta.json via put_file (best-effort, cloud mode only).
- Adoption / idempotent finalize: a reconciler finding running + past ceiling
  pulls <handle>/out when it exists and completes instead of failing; absent
  /out keeps the Item-3 failed leg (with a durably pushed tombstone —
  Round-2 amendment #1).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.orfs_client import JobExecution, OrfsRequest, OrfsResult
from src.platform_engines.orfs_runner import CloudJobOrfsRunner, set_orfs_runner
from src.platform_engines.workspace_provider import InMemoryObjectStore, make_run_stager
from src.tools import synthesis_manager as sm
from src.utils.session_context import SessionContext, session_scope


class RecordingStore(InMemoryObjectStore):
    """InMemoryObjectStore that records put_file keys (durable-push spy)."""

    def __init__(self) -> None:
        super().__init__()
        self.put_file_keys = []

    def put_file(self, key: str, local_path: str) -> None:
        self.put_file_keys.append(key)
        super().put_file(key, local_path)


@pytest.fixture
def durable_store():
    store = RecordingStore()
    sm.set_durable_run_store(store)
    try:
        yield store
    finally:
        sm.set_durable_run_store(None)


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _age_files(root: str, seconds_ago: float) -> None:
    import time as _time

    ts = _time.time() - seconds_ago
    for r, _dirs, files in os.walk(root):
        for name in files:
            os.utime(os.path.join(r, name), (ts, ts))


def _pushed_meta(store: RecordingStore, handle: str) -> dict:
    return json.loads(store._files[f"{handle}/meta/{sm.RUN_META_FILENAME}"])


# ---------------------------------------------------------------------------
# ObjectStore protocol additions
# ---------------------------------------------------------------------------


def test_inmemory_put_file_and_exists(tmp_path):
    store = InMemoryObjectStore()
    src = tmp_path / "run_meta.json"
    src.write_text('{"status": "running"}', encoding="utf-8")

    key = "sess-a/synth_0001/meta/run_meta.json"
    assert not store.exists(key)
    store.put_file(key, str(src))
    assert store.exists(key)
    assert store._files[key] == b'{"status": "running"}'

    # Tar keys are a separate spelling but share the same exists() check.
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_text("x", encoding="utf-8")
    store.put_tree("sess-a/synth_0001/out", str(tree))
    assert store.exists("sess-a/synth_0001/out")

    # get_tree keeps its silent empty-dir behavior for ABSENT blobs — that is
    # exactly why exists() must be the explicit adoption check.
    dest = tmp_path / "dest"
    store.get_tree("no/such/key", str(dest))
    assert os.path.isdir(dest) and os.listdir(dest) == []


def test_make_run_stager_honors_explicit_handle(tmp_path):
    store = InMemoryObjectStore()
    stage_in, stage_out = make_run_stager(store)
    run_dir = tmp_path / "synth_0001"
    run_dir.mkdir()
    (run_dir / "config.mk").write_text("export DESIGN_NAME = dut\n", encoding="utf-8")

    handle = stage_in(str(run_dir), "sess-a/synth_0001")
    assert handle == "sess-a/synth_0001"
    assert store.exists("sess-a/synth_0001")

    # Empty handle keeps the legacy unique mint (local/fallback path).
    minted = stage_in(str(run_dir))
    assert minted.startswith("synth_0001-") and store.exists(minted)


# ---------------------------------------------------------------------------
# Deterministic run handle through the OrfsRequest seam
# ---------------------------------------------------------------------------


def test_manager_passes_deterministic_handle_through_orfs_request(tmp_path):
    recorded = []

    class RecordingRunner:
        backend = "cloud_job"

        def run(self, request: OrfsRequest) -> OrfsResult:
            recorded.append(request)
            return OrfsResult(True, "ok", "", request.command, 0, self.backend)

    run_dir = tmp_path / "synth_runs" / "synth_0007"
    run_dir.mkdir(parents=True)
    set_orfs_runner(RecordingRunner())
    try:
        with session_scope(SessionContext("sess-handle", str(tmp_path))):
            sm._run_orfs_via_runner(str(run_dir), "make", [], timeout=60)
    finally:
        set_orfs_runner(None)

    assert len(recorded) == 1
    assert recorded[0].run_handle == "sess-handle/synth_0007"


def test_no_session_context_means_no_handle(tmp_path):
    assert sm._compute_run_handle(str(tmp_path / "synth_0001")) == ""


def test_cloud_runner_stages_under_request_run_handle(tmp_path):
    store = InMemoryObjectStore()
    stage_in, stage_out = make_run_stager(store)
    calls = []

    class FakeJobClient:
        def execute(self, job, env, args, timeout):
            calls.append(env)
            return JobExecution(succeeded=True, exit_code=0, stdout="done")

    runner = CloudJobOrfsRunner(job_client=FakeJobClient(), stage_in=stage_in, stage_out=stage_out)
    run_dir = tmp_path / "synth_0002"
    run_dir.mkdir()
    (run_dir / "config.mk").write_text("x\n", encoding="utf-8")

    result = runner.run(
        OrfsRequest(run_dir=str(run_dir), command="make", run_handle="s1/synth_0002")
    )

    assert result.success
    assert calls[0]["ORFS_RUN_HANDLE"] == "s1/synth_0002"  # no minted UUID
    assert store.exists("s1/synth_0002")


# ---------------------------------------------------------------------------
# Progressive meta push at worker milestones
# ---------------------------------------------------------------------------


def test_worker_milestones_push_meta_to_handle_prefix(tmp_path, durable_store):
    workspace = str(tmp_path)
    design = os.path.join(workspace, "counter.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write("module counter(input clk, output reg q); endmodule\n")
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)
    handle = "sess-push/synth_0001"
    args = {
        "run_id": "synth_0001",
        "top_module": "counter",
        "platform": "sky130hd",
        "max_stage": "constraints",  # stops before any ORFS execution
        "verilog_files": [design],
        "clock_period_ns": 10.0,
        "constraints_mode": "auto",
        "utilization": 40,
        "aspect_ratio": 1.0,
        "core_margin": 2.0,
        "timeout": 60,
    }

    with session_scope(SessionContext("sess-push", workspace)):
        sm._write_dispatch_meta(run_dir, "synth_0001", args, timeout_sec=600)
        assert durable_store.put_file_keys.count(f"{handle}/meta/{sm.RUN_META_FILENAME}") == 1
        assert _pushed_meta(durable_store, handle)["status"] == "queued"

        result = sm._job_worker(workspace, run_dir, args)

    assert result["status"] == "completed"
    # Dispatch + at least one worker milestone + finalize all pushed the meta.
    meta_pushes = durable_store.put_file_keys.count(f"{handle}/meta/{sm.RUN_META_FILENAME}")
    assert meta_pushes >= 3
    assert _pushed_meta(durable_store, handle)["status"] == "completed"


def test_push_is_noop_without_cloud_store(tmp_path):
    # Local mode: no store configured — the push must be a silent no-op.
    with session_scope(SessionContext("sess-local", str(tmp_path))):
        sm._push_durable_run_meta(str(tmp_path / "synth_0001"), {"status": "running"})


# ---------------------------------------------------------------------------
# Adoption / idempotent finalize in the reconciler
# ---------------------------------------------------------------------------


def _make_stale_run(workspace: str, run_id: str = "synth_0001", dispatched_ago: float = 2000.0):
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    meta = {
        "run_id": run_id,
        "status": "running",
        "dispatched_at": _iso_ago(dispatched_ago),
        "timeout_sec": 600,
        "top_module": "counter",
        "platform": "sky130hd",
        "backend": "cloud_job",
    }
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _age_files(run_dir, dispatched_ago)  # idle since dispatch — liveness cold
    return run_dir, meta


def test_reconciler_adopts_cloud_outputs_and_completes(tmp_path, durable_store):
    workspace = str(tmp_path)
    run_dir, meta = _make_stale_run(workspace)
    handle = "sess-adopt/synth_0001"

    # The Job uploaded its outputs under <handle>/out, but the orchestrating
    # instance died before stage_out — the finish report only exists remotely.
    job_out = tmp_path / "job_out"
    (job_out / "orfs_reports").mkdir(parents=True)
    (job_out / "orfs_reports" / "6_finish.rpt").write_text("wns max 0.12\n", encoding="utf-8")
    durable_store.put_tree(f"{handle}/out", str(job_out))

    with session_scope(SessionContext("sess-adopt", workspace)):
        out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    assert out["status"] == "completed"
    assert os.path.isfile(os.path.join(run_dir, "orfs_reports", "6_finish.rpt"))
    # Terminal truth was pushed durably too (amendment #1).
    assert _pushed_meta(durable_store, handle)["status"] == "completed"


def test_reconciler_fails_run_when_no_cloud_outputs(tmp_path, durable_store):
    workspace = str(tmp_path)
    run_dir, meta = _make_stale_run(workspace)
    handle = "sess-adopt/synth_0001"

    with session_scope(SessionContext("sess-adopt", workspace)):
        out = sm._reconcile_stale_status(run_dir, dict(meta), workspace=workspace, has_live_future=False)

    # Absent <handle>/out → the Item-3 failed leg is unchanged...
    assert out["status"] == "failed"
    assert "orchestrator lost" in out["check_notes"]
    # ...but the tombstone is persisted durably, not only in instance scratch.
    assert _pushed_meta(durable_store, handle)["status"] == "failed"
    # And adoption never invented artifacts.
    assert not os.path.isdir(os.path.join(run_dir, "orfs_reports"))


def test_adoption_is_noop_in_local_mode(tmp_path):
    # No durable store (local settings): adoption must decline silently.
    with session_scope(SessionContext("sess-local", str(tmp_path))):
        assert sm._try_adopt_cloud_outputs(str(tmp_path / "synth_0001"), {}) is False
