"""#5 — thread PATCH validates the model id (plans/followups-backlog.md).

The PATCH handler used to accept any string (only alias-normalized), so a
stale/typo'd id failed at SEND time rather than PICK time. It now 422s early on
an id outside the known set (catalogs + still-priced ids), while valid catalog
ids AND aliases keep working.
"""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api


def test_patch_thread_rejects_unknown_model_accepts_known_and_alias():
    c = TestClient(api.app)
    sid = c.post("/api/sessions", json={"name": "modeltest"}).json()["id"]
    try:
        tid = c.post(f"/api/sessions/{sid}/threads", json={"title": "t"}).json()["id"]

        # Bogus/typo'd id → 422 at pick time (not a silent send-time failure).
        r = c.patch(f"/api/sessions/{sid}/threads/{tid}", json={"model": "gpt-9000-typo"})
        assert r.status_code == 422

        # A current catalog id is accepted.
        assert c.patch(f"/api/sessions/{sid}/threads/{tid}",
                       json={"model": "claude-opus-4-8"}).status_code == 200
        # A valid alias still normalizes and is accepted (not rejected).
        assert c.patch(f"/api/sessions/{sid}/threads/{tid}",
                       json={"model": "gemini-3-flash-preview"}).status_code == 200
    finally:
        c.delete(f"/api/sessions/{sid}")
