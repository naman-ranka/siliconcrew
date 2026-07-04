"""F1: read-only endpoints must NOT sync (upload); mutating ones MUST (perf brief).

The hosted workbench was slow because ``run_scoped``'s ``finally`` called
``sync_workspace`` unconditionally — every read re-tarred+uploaded the whole
workspace (tens of seconds post-synth) and a stale read's sync could clobber a
concurrent write. This proves reads no longer upload and writes still do, and
that the self-host path (``sync_workspace=None``) is unchanged.
"""
import os

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.actions import build_actions_router

SID = "proj/sess"
DUT = "module counter(input clk, output reg [7:0] q); always @(posedge clk) q<=q+1; endmodule\n"


def _client(tmp_path, sync_workspace):
    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve, sync_workspace=sync_workspace))
    return TestClient(app), resolve(SID)


def test_reads_do_not_sync_writes_do(tmp_path):
    synced: list[str] = []
    c, ws = _client(tmp_path, sync_workspace=lambda sid: synced.append(sid))
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)

    # --- reads: NO sync ---
    assert c.get(f"/api/workspace/{SID}/manifest").status_code == 200
    assert c.get(f"/api/workspace/{SID}/runs").status_code == 200
    assert c.post(f"/api/workspace/{SID}/lint").status_code in (200, 400)  # no toolchain → 400 ok
    assert synced == [], f"a read uploaded the workspace: {synced}"

    # --- writes: sync exactly once per call ---
    c.get(f"/api/workspace/{SID}/manifest")  # seed manifest (still a read)
    assert synced == []

    r = c.put(f"/api/workspace/{SID}/manifest", json={"platform": "asap7"})
    assert r.status_code == 200 and synced == [SID]

    files = [("files", ("top.v", DUT, "text/plain"))]
    assert c.post(f"/api/workspace/{SID}/files", files=files).status_code == 200
    assert synced == [SID, SID]

    assert c.put(f"/api/workspace/{SID}/code/top.v", json={"content": DUT}).status_code == 200
    assert synced == [SID, SID, SID]


def test_workbench_snapshot_hydrates_once_no_sync(tmp_path):
    """F4: the snapshot resolves the workspace ONCE (not ~18×), never syncs, and
    returns manifest+runs+files+spec+code+report in one response."""
    base = str(tmp_path)
    resolves: list[str] = []
    synced: list[str] = []

    def resolve(session_id: str) -> str:
        resolves.append(session_id)
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve, sync_workspace=lambda sid: synced.append(sid)))
    c = TestClient(app)
    ws = os.path.join(base, SID)
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    with open(os.path.join(ws, "design_spec.yaml"), "w") as f:
        f.write("top: counter\n")
    # A loose report so the snapshot's report payload is exercised (shape check).
    with open(os.path.join(ws, "counter_report.md"), "w") as f:
        f.write("# report\n")

    r = c.get(f"/api/workspace/{SID}/workbench")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    # One hydration for the whole snapshot (the fan-out was ~18).
    assert resolves.count(SID) == 1, resolves
    assert synced == [], "snapshot (a read) must not upload"
    # Combined payload with the expected shapes.
    assert "manifest" in body and "runs" in body
    assert any(f["name"] == "counter.v" and f["type"] == "verilog" for f in body["files"])
    assert body["spec"] and body["spec"]["filename"] == "design_spec.yaml"
    assert any(cf["filename"] == "counter.v" for cf in body["code"])
    # Report payload must use run_id (frontend ReportData), NOT runId.
    assert body["report"] and "run_id" in body["report"] and "runId" not in body["report"]
    assert body["report"]["filename"] == "counter_report.md"


def test_self_host_no_sync_configured_is_unchanged(tmp_path):
    """Self-host wires sync_workspace=None: mutating endpoints still work and the
    finally is a no-op (no crash, behavior identical to before)."""
    c, ws = _client(tmp_path, sync_workspace=None)
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    c.get(f"/api/workspace/{SID}/manifest")
    r = c.put(f"/api/workspace/{SID}/manifest", json={"platform": "asap7"})
    assert r.status_code == 200
    assert r.json()["manifest"]["platform"] == "asap7"
