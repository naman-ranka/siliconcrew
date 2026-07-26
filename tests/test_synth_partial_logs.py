"""Live/partial log staging read path (Fix C).

A hosted ORFS Job now snapshots its logs/ tree to <handle>/logs_partial while it
runs (deploy/orfs_job/entrypoint.sh). The backend falls back to that snapshot
when a run has no staged-back final logs — so a live or timeout-killed run is
inspectable instead of showing an empty tail — and labels the source honestly as
partial. A completed run with real logs must ignore the partial snapshot.

Fakes only (InMemoryObjectStore), per tests/test_synth_hosted_durability.py.
"""
import os
import re
import time

import pytest

from src.platform_engines.workspace_provider import InMemoryObjectStore
from src.tools import synthesis_manager as sm
from src.tools.search_logs import search_logs
from src.utils.session_context import SessionContext, session_scope


@pytest.fixture
def durable_store():
    store = InMemoryObjectStore()
    sm.set_durable_run_store(store)
    try:
        yield store
    finally:
        sm.set_durable_run_store(None)


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_partial_tree(tmp_path, content: str, mtime_ago: float = 0.0) -> str:
    tree = tmp_path / "partial"
    log = tree / "sky130hd" / "counter" / "base" / "1_synth.log"
    _write(str(log), content)
    if mtime_ago:
        ts = time.time() - mtime_ago
        os.utime(str(log), (ts, ts))
    return str(tree)


def _run_dir(workspace: str, run_id: str = "synth_0001") -> str:
    d = os.path.join(workspace, "synth_runs", run_id)
    os.makedirs(d, exist_ok=True)
    return d


def _meta(run_id: str = "synth_0001") -> dict:
    return {
        "run_id": run_id,
        "status": "running",
        "top_module": "counter",
        "platform": "sky130hd",
        "max_stage": "finish",
        "backend": "cloud_job",
    }


def test_killed_run_surfaces_partial_logs(tmp_path, durable_store):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)  # NO orfs_logs — job killed before out.tar.gz
    handle = "sess-partial/synth_0001"
    durable_store.put_tree(
        f"{handle}/logs_partial",
        _make_partial_tree(tmp_path, "yosys finished\nDetailed Route 30%\n", mtime_ago=45.0),
    )

    with session_scope(SessionContext("sess-partial", workspace)):
        resp = sm._build_status_response(
            "synth_0001", run_dir, "running", _meta(), workspace=workspace
        )

    assert any("Detailed Route 30%" in ln for ln in resp["last_log_lines"])
    assert resp["last_log_source"].startswith("partial (updated ")
    # The label carries an honest staleness number (~45s), not a pretend-fresh 0.
    age = int(re.search(r"updated (\d+)s ago", resp["last_log_source"]).group(1))
    assert 40 <= age <= 300
    # It was materialized under the run dir for the log readers.
    assert os.path.isdir(os.path.join(run_dir, sm.PARTIAL_LOGS_DIRNAME))


def test_completed_run_prefers_final_logs(tmp_path, durable_store):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    _write(
        os.path.join(run_dir, "orfs_logs", "sky130hd", "counter", "base", "6_final.log"),
        "flow complete\n",
    )
    handle = "sess-final/synth_0001"
    durable_store.put_tree(
        f"{handle}/logs_partial", _make_partial_tree(tmp_path, "stale partial\n")
    )

    with session_scope(SessionContext("sess-final", workspace)):
        resp = sm._build_status_response(
            "synth_0001", run_dir, "completed", _meta(), workspace=workspace
        )

    assert any("flow complete" in ln for ln in resp["last_log_lines"])
    assert not any("stale partial" in ln for ln in resp["last_log_lines"])
    assert resp["last_log_source"] == "final"
    # Final logs present → the partial snapshot was never pulled.
    assert not os.path.isdir(os.path.join(run_dir, sm.PARTIAL_LOGS_DIRNAME))


def test_partial_logs_noop_without_cloud_store(tmp_path):
    # Local mode (no durable store): no fallback, no crash, honest "none".
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    with session_scope(SessionContext("sess-local", workspace)):
        assert sm.stage_partial_logs_for_read(run_dir) is None
        resp = sm._build_status_response(
            "synth_0001", run_dir, "running", _meta(), workspace=workspace
        )
    assert resp["last_log_lines"] == []
    assert resp["last_log_source"] == "none"


def test_search_logs_falls_back_to_partial(tmp_path, durable_store):
    workspace = str(tmp_path / "ws")
    _run_dir(workspace)
    handle = "sess-search/synth_0001"
    durable_store.put_tree(
        f"{handle}/logs_partial",
        _make_partial_tree(tmp_path, "ERROR: congestion overflow at 30%\n"),
    )

    with session_scope(SessionContext("sess-search", workspace)):
        out = search_logs("congestion overflow", workspace_dir=workspace, run_id="synth_0001")

    assert "congestion overflow" in out
