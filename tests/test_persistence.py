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


def test_set_source_template_persists_and_reads_via_select_star(store):
    """A fork's provenance JSON round-trips on the session row (SELECT *)."""
    now = datetime.datetime.now()
    store.upsert_session("fork1", "alice", "Fork 1", "m", None, now)
    # Absent by default (a normal session carries no provenance).
    assert store.get_session("fork1").get("source_template") is None
    payload = '{"id": "sync_fifo", "name": "Synchronous FIFO", "forked_at": "2026-07-08T00:00:00+00:00"}'
    store.set_source_template("fork1", payload, user_id="alice")
    assert store.get_session("fork1", user_id="alice")["source_template"] == payload


def test_set_source_template_is_owner_scoped(store):
    """A non-owner's write is a no-op (owner clause) — no cross-tenant scribble."""
    now = datetime.datetime.now()
    store.upsert_session("fork2", "alice", "Fork 2", "m", None, now)
    store.set_source_template("fork2", '{"id": "x"}', user_id="bob")  # wrong tenant
    assert store.get_session("fork2", user_id="alice").get("source_template") is None


def test_postgres_set_source_template_emits_owner_scoped_update():
    """Postgres parity: owner-scoped UPDATE with %s placeholders."""

    class FakeCursor:
        def __init__(self, sink):
            self.sink = sink

        def execute(self, sql, params=()):
            self.sink.append((sql, params))

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
    store.set_source_template("s1", '{"id":"x"}', user_id="alice")
    sql, params = sink[-1]
    assert "UPDATE session_metadata SET source_template = %s" in sql
    assert "WHERE session_id = %s AND user_id = %s" in sql
    assert params == ('{"id":"x"}', "s1", "alice")


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


# --- Wave 10: Postgres conversation-checkpoint purge (delete cascade) --------


class _RecordingCkptCursor:
    """Records executed SQL; can be told to raise for a specific table."""

    def __init__(self, sink, fail_table=None):
        self.sink = sink
        self.fail_table = fail_table

    def execute(self, sql, params=()):
        self.sink.append((sql, params))
        if self.fail_table and f"FROM {self.fail_table} " in sql:
            raise RuntimeError(f"relation {self.fail_table} does not exist")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _RecordingCkptConn:
    def __init__(self, sink, events, fail_table=None):
        self.sink = sink
        self.events = events
        self.fail_table = fail_table
        self.autocommit = False

    def cursor(self):
        return _RecordingCkptCursor(self.sink, self.fail_table)

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_delete_thread_checkpoints_issues_one_delete_per_table_with_any():
    sink, events = [], []
    store = PostgresMetadataStore(
        "postgres://x", connect=lambda dsn: _RecordingCkptConn(sink, events)
    )
    conn_holder = {}

    def _connect(dsn):
        conn_holder["conn"] = _RecordingCkptConn(sink, events)
        return conn_holder["conn"]

    store = PostgresMetadataStore("postgres://x", connect=_connect)
    store.delete_thread_checkpoints({"sess", "t1"})

    # One DELETE per checkpoint table, each ``thread_id = ANY(%s)`` with the ids.
    assert len(sink) == len(store._CKPT_TABLES)
    tables_hit = []
    for sql, params in sink:
        assert "DELETE FROM" in sql and "thread_id = ANY(%s)" in sql
        (ids_param,) = params
        assert sorted(ids_param) == ["sess", "t1"]
        tables_hit.append(sql.split("FROM ")[1].split(" ")[0])
    assert tuple(tables_hit) == store._CKPT_TABLES
    # Autocommit (review F3): each DELETE is independent — no shared
    # transaction to commit/rollback, so a mid-loop failure can't undo an
    # earlier table's delete.
    assert conn_holder["conn"].autocommit is True
    assert events == []  # no explicit commit/rollback under autocommit


def test_delete_thread_checkpoints_skips_failing_table_without_aborting_others():
    """A table whose DELETE fails (transient / absent) is skipped; the other
    tables' deletes still apply — autocommit isolates each (review F3)."""
    sink, events = [], []
    absent = "checkpoint_blobs"
    store = PostgresMetadataStore(
        "postgres://x",
        connect=lambda dsn: _RecordingCkptConn(sink, events, fail_table=absent),
    )
    store.delete_thread_checkpoints(["t1"])

    # Every table was attempted (the failing one did not abort the loop).
    attempted = [sql.split("FROM ")[1].split(" ")[0] for sql, _ in sink]
    assert set(attempted) == set(store._CKPT_TABLES)
    # No rollback that could undo a sibling table's already-applied delete.
    assert "rollback" not in events


def test_delete_thread_checkpoints_noop_on_empty_or_none_ids():
    sink, events = [], []
    calls = {"n": 0}

    def _connect(dsn):
        calls["n"] += 1
        return _RecordingCkptConn(sink, events)

    store = PostgresMetadataStore("postgres://x", connect=_connect)
    store.delete_thread_checkpoints([])
    store.delete_thread_checkpoints({None})
    store.delete_thread_checkpoints(None and [] or [None, None])
    # No ids → no connection opened, no SQL executed.
    assert calls["n"] == 0
    assert sink == []
