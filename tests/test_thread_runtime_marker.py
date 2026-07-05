"""The shell-level ``runtime`` marker on chat_threads (Phase 2a).

A thread carries which registered agent runtime owns it. This is generic
dispatch infra (see src/agents/runtime_registry.py), NOT a Codex primitive —
the column defaults to native and legacy rows backfill to it. These tests prove
the column round-trips in the store + manager, migrates onto a legacy DB, and —
end to end — that a *persisted* marker drives registry dispatch to an extension
and degrades to native when that extension is absent (removability).
"""
import datetime
import sqlite3

import pytest

from src.agents import runtime_registry as rr
from src.agents.runtime_registry import RuntimeDescriptor, RuntimeEvent, RuntimeTurnContext
from src.platform_engines.metadata_store import SqliteMetadataStore
from src.utils.session_manager import SessionManager


@pytest.fixture
def mgr(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"))


@pytest.fixture(autouse=True)
def clean_registry():
    rr.clear_extensions()
    yield
    rr.clear_extensions()


# --- column round-trips + default -------------------------------------------

def test_default_thread_runtime_is_native(mgr):
    mgr.create_session("design", user_id="alice")
    threads = mgr.list_threads("design", user_id="alice")
    assert threads[0]["runtime"] == rr.NATIVE_RUNTIME


def test_create_thread_with_runtime_and_set_runtime(tmp_path):
    store = SqliteMetadataStore(str(tmp_path / "state.db"))
    store.init_schema()
    now = datetime.datetime.now()
    store.upsert_session("s1", "alice", "S", "m", None, now)

    store.create_thread("th-codex", "s1", "alice", "Codex chat", "gpt", now, runtime="codex")
    assert store.get_thread("th-codex", user_id="alice")["runtime"] == "codex"

    # A native thread can be flipped via update_thread(runtime=...).
    store.create_thread("th-native", "s1", "alice", "Chat", "m", now)
    assert store.get_thread("th-native", user_id="alice")["runtime"] == "langchain"
    store.update_thread("th-native", user_id="alice", runtime="codex")
    assert store.get_thread("th-native", user_id="alice")["runtime"] == "codex"


def test_manager_set_thread_runtime(mgr):
    mgr.create_session("design", user_id="alice")
    mgr.set_thread_runtime("design", "codex", user_id="alice")
    assert mgr.get_thread("design", user_id="alice")["runtime"] == "codex"


# --- migration onto a legacy DB (no runtime column) -------------------------

def test_runtime_column_migrates_onto_legacy_db(tmp_path):
    db = str(tmp_path / "legacy.db")
    # Hand-build a pre-runtime chat_threads table, then let init_schema migrate.
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chat_threads (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
        "user_id TEXT, title TEXT, model TEXT, created_at TIMESTAMP, last_active TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO chat_threads (id, session_id, user_id, title) VALUES (?, ?, ?, ?)",
        ("old", "s1", "alice", "Legacy chat"),
    )
    conn.commit()
    conn.close()

    store = SqliteMetadataStore(db)
    store.init_schema()  # must ALTER TABLE ADD COLUMN runtime, backfilling native

    row = store.get_thread("old", user_id="alice")
    assert row is not None
    assert row["runtime"] == "langchain"  # legacy row backfilled to native default


# --- end to end: a persisted marker drives dispatch (removability) ----------

class _FakeCodex:
    async def run_turn(self, ctx: RuntimeTurnContext) -> None:
        await ctx.emit(RuntimeEvent.text(f"codex ran for thread {ctx.thread_id}"))


def test_persisted_codex_marker_routes_to_extension(mgr):
    mgr.create_session("design", user_id="alice")
    mgr.set_thread_runtime("design", "codex", user_id="alice")
    row = mgr.get_thread("design", user_id="alice")

    # No extension registered yet: the stored 'codex' marker degrades to native.
    assert rr.resolve_runtime(row) == rr.NATIVE_RUNTIME
    assert rr.handler_for(rr.resolve_runtime(row)) is None

    # Register the Codex extension: the SAME persisted row now routes to it.
    rr.register_runtime(RuntimeDescriptor(id="codex", display_name="Codex"), _FakeCodex())
    assert rr.resolve_runtime(row) == "codex"
    assert isinstance(rr.handler_for(rr.resolve_runtime(row)), _FakeCodex)

    # Remove the extension: the persisted row silently degrades back to native.
    rr.unregister_runtime("codex")
    assert rr.resolve_runtime(row) == rr.NATIVE_RUNTIME
