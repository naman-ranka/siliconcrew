"""Wave S0 backend micro-wave: session rename, project rename, thread_count.

Covers all three layers, following the existing test patterns:
  * MetadataStore (SQLite) — tenant scoping, per test_tenancy_redteam.py
  * SessionManager — display-only rename semantics, per test_projects.py
  * API — TestClient over ``api.app`` with a temp SessionManager swapped in
  * PostgresMetadataStore — SQL-shape smoke via a recording fake connection,
    per test_persistence.py (mirror check for the new store methods)
"""
import datetime
import os

import pytest

from src.platform_engines.metadata_store import (
    PostgresMetadataStore,
    SqliteMetadataStore,
)
from src.utils.session_manager import SessionManager


# ---------------------------------------------------------------------------
# Store level (SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "state.db"))
    s.init_schema()
    return s


def test_store_rename_session_is_tenant_scoped(store):
    now = datetime.datetime.now()
    store.upsert_session("alice_sess", "alice", "orig", "m", None, now)
    # A valid OTHER user's rename is a no-op (scoped UPDATE matches 0 rows).
    store.rename_session("alice_sess", "hijacked", user_id="bob")
    assert store.get_session("alice_sess", user_id="alice")["session_name"] == "orig"
    # Owner rename works; the primary key (session_id) is untouched.
    store.rename_session("alice_sess", "renamed", user_id="alice")
    row = store.get_session("alice_sess", user_id="alice")
    assert row["session_id"] == "alice_sess"
    assert row["session_name"] == "renamed"


def test_store_rename_project_is_tenant_scoped(store):
    now = datetime.datetime.now()
    store.create_project("proj", "Proj", now, user_id="alice")
    store.rename_project("proj", "hijacked", user_id="bob")  # no-op
    assert store.get_project("proj", user_id="alice")["name"] == "Proj"
    store.rename_project("proj", "Proj v2", user_id="alice")
    assert store.get_project("proj", user_id="alice")["name"] == "Proj v2"


def test_store_count_threads_by_session_grouped_and_scoped(store):
    now = datetime.datetime.now()
    store.create_thread("t1", "s1", "alice", "Chat 1", None, now)
    store.create_thread("t2", "s1", "alice", "Chat 2", None, now)
    store.create_thread("t3", "s2", "alice", "Chat 1", None, now)
    store.create_thread("t4", "s3", "bob", "Chat 1", None, now)
    # Unscoped (self-host): every session's row count.
    assert store.count_threads_by_session() == {"s1": 2, "s2": 1, "s3": 1}
    # Tenant-scoped: only that user's thread rows are counted.
    assert store.count_threads_by_session(user_id="alice") == {"s1": 2, "s2": 1}
    assert store.count_threads_by_session(user_id="bob") == {"s3": 1}


# ---------------------------------------------------------------------------
# SessionManager level
# ---------------------------------------------------------------------------


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


def test_manager_rename_session_is_display_only(sm):
    sid = sm.create_session("fifo")
    ws = sm.get_workspace_path(sid)
    sm.rename_session(sid, "Sync FIFO")
    # Display name changed…
    assert sm.get_session_metadata(sid)["session_name"] == "Sync FIFO"
    # …but the id and workspace directory are untouched (rename never moves files).
    assert sid in sm.get_all_sessions()
    assert os.path.isdir(ws)
    assert sm.get_workspace_path(sid) == ws


def test_manager_rename_project_keeps_slug_and_sessions(sm):
    sm.create_project("My Project")  # slug "MyProject"
    sid = sm.create_session("blk", project_id="MyProject")
    sm.rename_project("MyProject", "Tapeout Q3")
    p = sm.get_project("MyProject")
    assert p["id"] == "MyProject" and p["name"] == "Tapeout Q3"
    # Sessions keep their project assignment (slug is immutable).
    assert sm.get_session_metadata(sid)["project_id"] == "MyProject"


def test_manager_thread_list_is_read_only_and_creation_seeds_chat_one(sm):
    sid = sm.create_session("quiet")
    # Wave 8: "Chat 1" is seeded at CREATION (count 1 from birth) and listing
    # is read-only — browsing (drawer/quick-switch/nav rail) never mutates.
    assert sm.count_threads_by_session()[sid] == 1
    sm.list_threads(sid)
    sm.list_threads(sid)
    assert sm.count_threads_by_session()[sid] == 1  # no ensure side effects


# ---------------------------------------------------------------------------
# API level (TestClient over api.app with a temp SessionManager swapped in)
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

import api  # noqa: E402


@pytest.fixture
def client(sm, monkeypatch):
    monkeypatch.setattr(api, "session_manager", sm)
    return TestClient(api.app)


def test_api_rename_session_persists_id_unchanged(client, sm):
    sid = sm.create_session("uart_tx")
    ws = sm.get_workspace_path(sid)

    r = client.patch(f"/api/sessions/{sid}", json={"name": "UART transmitter"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == sid  # rename is display-only: id never changes
    assert body["name"] == "UART transmitter"

    # Persists in the list…
    items = {s["id"]: s for s in client.get("/api/sessions").json()}
    assert items[sid]["name"] == "UART transmitter"
    # …and in the single GET.
    assert client.get(f"/api/sessions/{sid}").json()["name"] == "UART transmitter"
    # Workspace directory untouched.
    assert os.path.isdir(ws)


def test_api_rename_session_preserves_project_assignment(client, sm):
    sm.create_project("grp")
    sid = sm.create_session("blk", project_id="grp")  # id "grp/blk" (has a slash)
    r = client.patch(f"/api/sessions/{sid}", json={"name": "Block A"})
    assert r.status_code == 200, r.text
    # A pure rename must NOT clear project_id (field-absent != explicit null).
    assert r.json()["project_id"] == "grp"
    assert r.json()["name"] == "Block A"


def test_api_patch_session_empty_body_is_400(client, sm):
    sid = sm.create_session("s1")
    r = client.patch(f"/api/sessions/{sid}", json={})
    assert r.status_code == 400
    # And the explicit-null project removal still works (not an empty patch).
    sm.create_project("g")
    sm.move_session_to_project(sid, "g")
    r = client.patch(f"/api/sessions/{sid}", json={"project_id": None})
    assert r.status_code == 200
    assert r.json()["project_id"] is None


def test_api_patch_session_blank_name_is_400(client, sm):
    sid = sm.create_session("s2")
    r = client.patch(f"/api/sessions/{sid}", json={"name": "   "})
    assert r.status_code == 400
    assert sm.get_session_metadata(sid)["session_name"] == "s2"


def test_api_rename_session_respects_ownership(client, sm, monkeypatch):
    """Tenancy: a valid OTHER user gets 404, never a rename (redteam pattern)."""
    sm.create_session("secret", user_id="alice")

    monkeypatch.setattr(api, "_uid", lambda identity: "bob")
    r = client.patch("/api/sessions/secret", json={"name": "hijacked"})
    assert r.status_code == 404
    assert sm.get_session_metadata("secret", user_id="alice")["session_name"] == "secret"

    monkeypatch.setattr(api, "_uid", lambda identity: "alice")
    r = client.patch("/api/sessions/secret", json={"name": "mine"})
    assert r.status_code == 200
    assert sm.get_session_metadata("secret", user_id="alice")["session_name"] == "mine"


def test_api_rename_project_persists(client, sm):
    sm.create_project("Alpha")
    r = client.patch("/api/projects/Alpha", json={"name": "Alpha v2"})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "Alpha", "name": "Alpha v2", "created_at": r.json()["created_at"]}
    names = {p["id"]: p["name"] for p in client.get("/api/projects").json()}
    assert names["Alpha"] == "Alpha v2"


def test_api_rename_missing_project_404(client, sm):
    r = client.patch("/api/projects/ghost", json={"name": "whatever"})
    assert r.status_code == 404


def test_api_thread_count_fresh_session_is_one(client, sm):
    sid = sm.create_session("fresh")
    items = {s["id"]: s for s in client.get("/api/sessions").json()}
    # Honest count: creation seeds the default "Chat 1" row (Wave 8), so a
    # fresh session reports 1 — and the session list still never ensures
    # anything itself (it just COUNTs the table).
    assert items[sid]["thread_count"] == 1


def test_api_create_session_response_reports_seeded_thread_count(client, sm):
    # The POST response itself must agree with later list/GET reads (1, the
    # seeded Chat 1) — a defaulted 0 would leave the client stale.
    r = client.post("/api/sessions", json={"name": "born", "model": "gemini-3-flash-preview"})
    assert r.status_code == 200, r.text
    assert r.json()["thread_count"] == 1


def test_api_thread_count_reflects_created_threads(client, sm):
    sid = sm.create_session("busy")
    # Creating a thread first ensure-creates the default "Chat 1" row (so the
    # legacy conversation keyed by session_id stays reachable), THEN adds the
    # new thread. Two POSTs therefore leave 3 rows: Chat 1 + 2 new threads.
    assert client.post(f"/api/sessions/{sid}/threads", json={}).status_code == 201
    assert client.post(f"/api/sessions/{sid}/threads", json={}).status_code == 201

    items = {s["id"]: s for s in client.get("/api/sessions").json()}
    assert items[sid]["thread_count"] == 3
    # Single GET agrees (same honest COUNT).
    assert client.get(f"/api/sessions/{sid}").json()["thread_count"] == 3


# ---------------------------------------------------------------------------
# Postgres mirror: the new methods emit %s SQL against the right tables
# (recording-fake pattern from test_persistence.py; a live Postgres parity run
# is a deploy-time check).
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, sink):
        self.sink = sink
        self.description = [("session_id",), ("count",)]

    def execute(self, sql, params=()):
        self.sink.append((sql, params))

    def fetchone(self):
        return ("s1", 2)

    def fetchall(self):
        return [("s1", 2), ("s2", 1)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, sink):
        self.sink = sink

    def cursor(self):
        return _FakeCursor(self.sink)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_postgres_store_mirrors_new_methods():
    sink = []
    store = PostgresMetadataStore("postgres://x", connect=lambda dsn: _FakeConn(sink))

    store.rename_session("s1", "New Name", user_id="alice")
    sql, params = sink[-1]
    assert "UPDATE session_metadata SET session_name = %s" in sql
    assert "user_id = %s" in sql and params == ("New Name", "s1", "alice")

    store.rename_project("p1", "New Proj")
    sql, params = sink[-1]
    assert "UPDATE projects SET name = %s" in sql and params == ("New Proj", "p1")

    counts = store.count_threads_by_session(user_id="alice")
    sql, params = sink[-1]
    assert "GROUP BY session_id" in sql and "chat_threads" in sql
    assert "user_id = %s" in sql and params == ("alice",)
    assert counts == {"s1": 2, "s2": 1}


def test_thread_routes_not_shadowed_by_greedy_session_patch():
    """Regression: PATCH/DELETE /api/sessions/{sid:path} must be registered
    AFTER the /threads sub-routes — the greedy :path converter otherwise binds
    session_id="<sid>/threads/<tid>" and 404s, silently breaking thread rename
    and per-thread model switching over REST."""
    from fastapi.testclient import TestClient
    import api as api_mod

    c = TestClient(api_mod.app)
    sid = c.post("/api/sessions", json={"name": "shadowtest", "model": "gemini-3-flash-preview"}).json()["id"]
    try:
        tid = c.post(f"/api/sessions/{sid}/threads", json={"title": "t"}).json()["id"]
        assert c.patch(f"/api/sessions/{sid}/threads/{tid}", json={"title": "renamed"}).status_code == 200
        assert c.patch(f"/api/sessions/{sid}/threads/{tid}", json={"model": "claude-sonnet-4-6"}).status_code == 200
        assert c.delete(f"/api/sessions/{sid}/threads/{tid}").status_code == 200
    finally:
        c.delete(f"/api/sessions/{sid}")
