"""WorkspaceProvider local/cloud parity (Phase 2, slice 3).

The cloud provider must give the tools the same thing the local one does — a
real POSIX directory they can read and write — while transparently round-tripping
through object storage. No GCP: an in-memory tar-blob store stands in.
"""
import os

from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
    make_run_stager,
)
from src.utils.session_context import LocalWorkspaceProvider


def _write(ws: str, name: str, content: str) -> None:
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(content)


def test_both_providers_yield_a_writable_posix_dir(tmp_path):
    local = LocalWorkspaceProvider(str(tmp_path / "local"))
    cloud = CloudWorkspaceProvider(InMemoryObjectStore(), str(tmp_path / "scratch"))

    for provider in (local, cloud):
        ws = provider.workspace_for("sess_a")
        assert os.path.isdir(ws)
        _write(ws, "design.v", "module a; endmodule\n")
        assert os.path.isfile(os.path.join(ws, "design.v"))


def test_cloud_provider_round_trips_through_object_storage(tmp_path):
    """Write → sync → fresh process/scratch → workspace_for restores the files."""
    store = InMemoryObjectStore()

    # Request 1: create + write + sync back.
    p1 = CloudWorkspaceProvider(store, str(tmp_path / "scratch1"))
    ws1 = p1.workspace_for("sess_b")
    _write(ws1, "top.v", "module top; endmodule\n")
    os.makedirs(os.path.join(ws1, "synth_runs", "synth_0001"), exist_ok=True)
    _write(os.path.join(ws1, "synth_runs", "synth_0001"), "run_meta.json", "{}")
    p1.sync("sess_b")

    # Request 2: a brand-new provider with a brand-new scratch dir (simulating a
    # different Cloud Run instance) must see the persisted tree.
    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("sess_b")
    assert os.path.isfile(os.path.join(ws2, "top.v"))
    assert os.path.isfile(os.path.join(ws2, "synth_runs", "synth_0001", "run_meta.json"))


def test_cloud_provider_isolates_sessions(tmp_path):
    store = InMemoryObjectStore()
    provider = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    wsa = provider.workspace_for("alice")
    _write(wsa, "alice.v", "// alice\n")
    provider.sync("alice")
    wsb = provider.workspace_for("bob")
    _write(wsb, "bob.v", "// bob\n")
    provider.sync("bob")

    # A fresh provider must not see cross-session files.
    fresh = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    a = fresh.workspace_for("alice")
    assert os.listdir(a) == ["alice.v"]
    b = fresh.workspace_for("bob")
    assert os.listdir(b) == ["bob.v"]


def test_run_stager_round_trips_result_subdirs(tmp_path):
    """stage_in uploads the run dir; the 'Job' uploads results; stage_out pulls them."""
    store = InMemoryObjectStore()
    stage_in, stage_out = make_run_stager(store)

    run_dir = tmp_path / "synth_0003"
    (run_dir / "inputs").mkdir(parents=True)
    _write(str(run_dir / "inputs"), "dut.v", "module dut; endmodule\n")
    _write(str(run_dir), "config.mk", "export DESIGN_NAME = dut\n")

    handle = stage_in(str(run_dir))
    assert store.exists(handle)

    # Simulate the Cloud Run Job producing results and uploading under "<handle>/out".
    job_out = tmp_path / "job_out"
    (job_out / "orfs_reports").mkdir(parents=True)
    _write(str(job_out / "orfs_reports"), "6_finish.rpt", "wns max 0.12\n")
    store.put_tree(f"{handle}/out", str(job_out))

    # stage_out pulls the produced artifacts back into the local run dir.
    stage_out(str(run_dir), handle)
    assert os.path.isfile(str(run_dir / "orfs_reports" / "6_finish.rpt"))


def test_extract_rejects_path_traversal(tmp_path):
    import io
    import tarfile
    import pytest

    store = InMemoryObjectStore()
    # Hand-craft a malicious tar with a traversal member.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="../escape.txt")
        data = b"pwned"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    store._blobs["evil"] = buf.getvalue()

    with pytest.raises(ValueError, match="path-traversal"):
        store.get_tree("evil", str(tmp_path / "dest"))
