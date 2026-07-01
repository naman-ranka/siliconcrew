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
