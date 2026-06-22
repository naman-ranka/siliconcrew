"""MetadataStore contract (Phase 2, slice 6).

Runs the relational operations SessionManager depends on against the SQLite
store. The same contract is what PostgresMetadataStore implements, so Cloud SQL
is a config swap. (A live Postgres parity run is a deploy-time check.)
"""
import datetime

import pytest

from src.platform_engines.metadata_store import (
    DuplicateProject,
    PostgresMetadataStore,
    SqliteMetadataStore,
)


@pytest.fixture
def store(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "state.db"))
    s.init_schema()
    return s


def test_init_schema_is_idempotent(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "state.db"))
    s.init_schema()
    s.init_schema()  # no raise — CREATE IF NOT EXISTS + guarded migrations


def test_project_crud_and_duplicate(store):
    now = datetime.datetime.now()
    store.create_project("alpha", "Alpha", now)
    assert store.get_project("alpha")["name"] == "Alpha"
    assert [p["id"] for p in store.get_all_projects()] == ["alpha"]
    with pytest.raises(DuplicateProject):
        store.create_project("alpha", "Alpha again", now)


def test_session_upsert_preserves_existing_name_and_project(store):
    now = datetime.datetime.now()
    store.create_project("proj", "Proj", now)
    # Signature: upsert_session(session_id, user_id, session_name, model_name, project_id, now)
    store.upsert_session("proj/s1", None, "s1", "gemini-3-flash-preview", "proj", now)
    # A later upsert with NULLs must NOT clobber existing name/project (COALESCE).
    store.upsert_session("proj/s1", None, None, None, None, now)
    row = store.get_session("proj/s1")
    assert row["session_name"] == "s1"
    assert row["project_id"] == "proj"
    assert row["model_name"] == "gemini-3-flash-preview"


def test_delete_project_unassigns_sessions(store):
    now = datetime.datetime.now()
    store.create_project("proj", "Proj", now)
    store.upsert_session("proj/s1", None, "s1", "m", "proj", now)
    store.delete_project("proj")
    assert store.get_project("proj") is None
    # Session survives, now unassigned.
    assert store.get_session("proj/s1")["project_id"] is None


def test_update_stats_and_move(store):
    now = datetime.datetime.now()
    store.create_project("p2", "P2", now)
    store.upsert_session("s2", None, "s2", "m", None, now)
    store.update_stats("s2", 10, 20, 5, 35, 0.42, now)
    row = store.get_session("s2")
    assert row["input_tokens"] == 10 and row["total_tokens"] == 35 and row["total_cost"] == 0.42
    store.move_session("s2", "p2")
    assert store.get_session("s2")["project_id"] == "p2"


def test_delete_session(store):
    now = datetime.datetime.now()
    store.upsert_session("gone", None, "gone", "m", None, now)
    store.delete_session("gone")
    assert store.get_session("gone") is None


def test_legacy_group_migration(tmp_path):
    """A pre-existing 'project/session' row gets promoted to a project_id FK."""
    import sqlite3

    db = str(tmp_path / "legacy.db")
    # Simulate the OLD schema (no project_id column) with a grouped session.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE session_metadata (session_id TEXT PRIMARY KEY, session_name TEXT, "
            "model_name TEXT, created_at TIMESTAMP, updated_at TIMESTAMP, "
            "input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER, "
            "total_tokens INTEGER, total_cost REAL)"
        )
        conn.execute("INSERT INTO session_metadata (session_id) VALUES ('myproj/sess1')")
        conn.commit()

    SqliteMetadataStore(db).init_schema()  # triggers the migration
    s = SqliteMetadataStore(db)
    assert s.get_project("myproj") is not None
    assert s.get_session("myproj/sess1")["project_id"] == "myproj"


def test_postgres_store_uses_injected_connection_and_emits_pct_s_sql():
    """Smoke the Postgres store's SQL shape via a recording fake connection."""

    class FakeCursor:
        def __init__(self, sink):
            self.sink = sink
            self.description = [("session_id",)]

        def execute(self, sql, params=()):
            self.sink.append((sql, params))

        def fetchone(self):
            return ("s1",)

        def fetchall(self):
            return [("s1",)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeConn:
        def __init__(self, sink):
            self.sink = sink

        def cursor(self):
            return FakeCursor(self.sink)

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    sink = []
    store = PostgresMetadataStore("postgres://x", connect=lambda dsn: FakeConn(sink))
    store.get_session("s1")
    sql, params = sink[-1]
    assert "%s" in sql and "session_metadata" in sql and params == ("s1",)
