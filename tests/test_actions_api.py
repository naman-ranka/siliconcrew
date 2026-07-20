"""API smoke tests for the Phase 1 action router (no agent stack required).

Mounts ``build_actions_router`` on a bare FastAPI app pointed at a temp
workspace and hits every endpoint. EDA-dependent paths (real lint/sim) are
exercised only where the toolchain exists; the manifest/runs/pin endpoints run
everywhere.
"""
import os
import shutil

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.actions import build_actions_router

SID = "proj/sess"  # exercise the :path session id (slashes allowed)

DUT = "module counter(input clk, output reg [7:0] q); initial q=0; always @(posedge clk) q<=q+1; endmodule\n"
TB = ('module counter_tb; reg clk=0; wire [7:0] q; counter d(.clk(clk),.q(q));\n'
      'always #5 clk=~clk;\n'
      'initial begin $dumpfile("dump.vcd"); $dumpvars(0,counter_tb); #40 $display("TEST PASSED"); $finish; end endmodule\n')


@pytest.fixture()
def client(tmp_path):
    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    return TestClient(app), resolve(SID)


def test_manifest_get_autoderives(client):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    with open(os.path.join(ws, "counter_tb.v"), "w") as f:
        f.write(TB)

    r = c.get(f"/api/workspace/{SID}/manifest")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    man = body["manifest"]
    assert man["simTop"] == "counter_tb"
    assert man["synthTop"] == "counter"
    roles = {f["name"]: f["role"] for f in man["files"]}
    assert roles == {"counter.v": "rtl", "counter_tb.v": "tb"}


def test_manifest_put_overrides(client):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    c.get(f"/api/workspace/{SID}/manifest")

    r = c.put(f"/api/workspace/{SID}/manifest", json={"platform": "asap7", "clockPeriodNs": 5.0})
    assert r.status_code == 200
    man = r.json()["manifest"]
    assert man["platform"] == "asap7"
    assert man["clockPeriodNs"] == 5.0


def test_file_upload_then_manifest_tags_roles(client):
    c, ws = client
    files = [
        ("files", ("counter.v", DUT, "text/plain")),
        ("files", ("counter_tb.v", TB, "text/plain")),
    ]
    r = c.post(f"/api/workspace/{SID}/files", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["uploaded"]) == {"counter.v", "counter_tb.v"}
    assert os.path.exists(os.path.join(ws, "counter.v"))
    roles = {f["name"]: f["role"] for f in body["manifest"]["files"]}
    assert roles["counter_tb.v"] == "tb"


def test_simulate_requires_sim_top(client):
    c, ws = client
    # empty workspace → no simTop, no files
    r = c.post(f"/api/workspace/{SID}/simulate", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] in {"no_sim_top", "no_files"}


def test_save_code_writes_file_and_returns_manifest(client):
    c, ws = client
    # create via the in-app editor path
    r = c.put(f"/api/workspace/{SID}/code/counter.v", json={"content": DUT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["saved"] == "counter.v"
    assert os.path.exists(os.path.join(ws, "counter.v"))
    assert any(f["name"] == "counter.v" and f["role"] == "rtl" for f in body["manifest"]["files"])

    # edit the same file — content is overwritten
    r2 = c.put(f"/api/workspace/{SID}/code/counter.v", json={"content": "// edited\n" + DUT})
    assert r2.status_code == 200
    with open(os.path.join(ws, "counter.v")) as f:
        assert f.read().startswith("// edited")


def test_save_code_rejects_path_traversal(client):
    c, ws = client
    r = c.put(f"/api/workspace/{SID}/code/..%2f..%2fevil.v", json={"content": "x"})
    # the shared file_ops.write_file guard rejects an escape (400), never writes outside
    assert r.status_code == 400
    assert not os.path.exists(os.path.join(os.path.dirname(ws), "evil.v"))


def test_runs_empty_ok(client):
    c, ws = client
    r = c.get(f"/api/workspace/{SID}/runs")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "runs": []}


def test_pin_missing_run_404(client):
    c, ws = client
    r = c.post(f"/api/workspace/{SID}/runs/sim_9999/pin", json={"pinned": True})
    assert r.status_code == 404


def test_concurrent_sessions_are_workspace_isolated(tmp_path):
    """Two sessions hit the action layer concurrently and must not see each
    other's files — the load-bearing cross-tenant seam (session_scope per
    request, never the global env var)."""
    from concurrent.futures import ThreadPoolExecutor

    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    c = TestClient(app)

    # Distinct designs in two sessions.
    with open(os.path.join(resolve("alice"), "alice_top.v"), "w") as f:
        f.write("module alice_top(input a); endmodule\n")
    with open(os.path.join(resolve("bob"), "bob_top.v"), "w") as f:
        f.write("module bob_top(input b); endmodule\n")

    def fetch(sid: str):
        return c.get(f"/api/workspace/{sid}/manifest").json()["manifest"]

    with ThreadPoolExecutor(max_workers=2) as ex:
        ma, mb = ex.map(fetch, ["alice", "bob"])

    names_a = {f["name"] for f in ma["files"]}
    names_b = {f["name"] for f in mb["files"]}
    assert names_a == {"alice_top.v"}
    assert names_b == {"bob_top.v"}  # no cross-tenant bleed


def test_action_writes_persist_through_workspace_provider(tmp_path):
    """Regression (hosted data loss): the directory the action router writes to
    MUST be the directory ``sync`` persists back to object storage.

    The bug wired ``resolve_workspace`` to the local ``base_dir`` while
    ``sync_workspace`` uploaded the provider's scratch dir — so in hosted mode
    every save/upload/sim/synth output was written to one directory and a
    *different*, empty directory was uploaded, silently dropping user work.
    Both must flow through the same WorkspaceProvider.
    """
    from src.platform_engines.workspace_provider import (
        CloudWorkspaceProvider,
        InMemoryObjectStore,
    )

    store = InMemoryObjectStore()
    provider = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    app = FastAPI()
    app.include_router(build_actions_router(
        provider.workspace_for,
        sync_workspace=provider.sync,
    ))
    c = TestClient(app)

    r = c.put(f"/api/workspace/{SID}/code/counter.v", json={"content": DUT})
    assert r.status_code == 200, r.text

    # The write landed in exactly the dir the provider syncs (its scratch path),
    # not a divergent local base_dir.
    assert os.path.exists(os.path.join(provider._scratch(SID), "counter.v"))

    # ...and sync actually persisted it: a fresh materialize (new scratch, same
    # object store) recovers the write — the round-trip the bug silently broke.
    fresh = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    recovered = fresh.workspace_for(SID)
    with open(os.path.join(recovered, "counter.v")) as f:
        assert f.read() == DUT


@pytest.mark.requires_eda
@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_lint_and_simulate_end_to_end(client):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    with open(os.path.join(ws, "counter_tb.v"), "w") as f:
        f.write(TB)
    c.get(f"/api/workspace/{SID}/manifest")

    lint = c.post(f"/api/workspace/{SID}/lint").json()
    assert lint["ok"] is True
    assert lint["status"] == "passed"
    assert any(e in lint["command"] for e in ("iverilog", "verilator"))  # auto picks the best installed engine

    sim = c.post(f"/api/workspace/{SID}/simulate", json={}).json()
    assert sim["ok"] is True
    run = sim["run"]
    assert run["id"] == "sim_0001"
    assert run["kind"] == "sim"
    assert run["vcdPath"].endswith(".vcd")
    assert os.path.exists(os.path.join(ws, run["vcdPath"]))

    runs = c.get(f"/api/workspace/{SID}/runs").json()["runs"]
    assert any(r["id"] == "sim_0001" for r in runs)
