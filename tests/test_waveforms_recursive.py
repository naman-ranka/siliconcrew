"""#4 — GET /waveforms lists workspace VCDs recursively (followups-backlog.md).

The endpoint used a non-recursive ``os.listdir``, so it never saw
``sim_runs/**`` or any subdirectory VCD — a dishonest "list VCD files in the
workspace". A nested sim-run dump must now be listed (as a workspace-relative
path so it stays fetchable via the sibling /waveform/{filename:path} route).
"""
import os

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api


def test_waveforms_lists_nested_vcd_recursively():
    c = TestClient(api.app)
    sid = c.post("/api/sessions", json={"name": "wavetest"}).json()["id"]
    try:
        ws = api._resolve_workspace(sid)
        os.makedirs(os.path.join(ws, "sim_runs", "sim_0001"), exist_ok=True)
        for rel in ("root.vcd", "sim_runs/sim_0001/dump.vcd"):
            with open(os.path.join(ws, rel), "w", encoding="utf-8") as f:
                f.write("$date\n")

        r = c.get(f"/api/workspace/{sid}/waveforms")
        assert r.status_code == 200
        listed = r.json()
        assert "root.vcd" in listed
        # the nested sim-run VCD the old non-recursive listdir missed:
        assert "sim_runs/sim_0001/dump.vcd" in listed
    finally:
        c.delete(f"/api/sessions/{sid}")
