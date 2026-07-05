"""Codex-owned transcript + thread-map store (Phase 2a).

Codex has no checkpointer, so it persists its own history. These cover the
transcript CRUD, the external-thread-id map (Codex resume), ordering,
tool_metadata round-trip, and the cleanup used by the thread-deleted hook.
"""
import datetime

import pytest

from src.agents.codex.codex_store import SqliteCodexStore, build_codex_store
from src.platform_engines.metadata_store import SqliteMetadataStore


@pytest.fixture
def stores(tmp_path):
    db = str(tmp_path / "state.db")
    meta = SqliteMetadataStore(db)
    meta.init_schema()
    now = datetime.datetime.now()
    meta.upsert_session("s1", "alice", "S", "m", None, now)
    meta.create_thread("th1", "s1", "alice", "Codex chat", "gpt", now, runtime="codex")
    codex = SqliteCodexStore(db)
    codex.init_schema()
    return meta, codex


# --- external thread id map (resume) ----------------------------------------

def test_external_thread_id_set_get_upsert(stores):
    _, codex = stores
    assert codex.get_external_thread_id("th1") is None
    codex.set_external_thread_id("th1", "ext-123")
    assert codex.get_external_thread_id("th1") == "ext-123"
    # Upsert (same thread, new external id) overwrites, not duplicates.
    codex.set_external_thread_id("th1", "ext-456")
    assert codex.get_external_thread_id("th1") == "ext-456"


# --- transcript CRUD + ordering + tool_metadata -----------------------------

def test_append_and_list_messages_ordered(stores):
    _, codex = stores
    t0 = datetime.datetime(2026, 1, 1, 10, 0, 0)
    t1 = datetime.datetime(2026, 1, 1, 10, 0, 1)
    codex.append_message("th1", "user", "hello", created_at=t0)
    codex.append_message(
        "th1", "assistant", "hi there",
        tool_metadata={"tool_calls": [{"id": "c1", "name": "read_file"}], "tool_results": []},
        created_at=t1,
    )
    msgs = codex.list_messages("th1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hello"
    # tool_metadata round-trips as a dict, not a JSON string.
    assert msgs[1]["tool_metadata"]["tool_calls"][0]["name"] == "read_file"


def test_append_returns_decoded_message(stores):
    _, codex = stores
    out = codex.append_message("th1", "assistant", "x", tool_metadata={"k": "v"})
    assert out["tool_metadata"] == {"k": "v"}
    assert out["role"] == "assistant"


def test_list_messages_empty_for_unknown_thread(stores):
    _, codex = stores
    assert codex.list_messages("nope") == []
    assert codex.get_external_thread_id("nope") is None


# --- cleanup (the thread-deleted hook target) -------------------------------

def test_delete_for_thread_clears_transcript_and_map(stores):
    _, codex = stores
    codex.set_external_thread_id("th1", "ext-1")
    codex.append_message("th1", "user", "a")
    codex.append_message("th1", "assistant", "b")

    codex.delete_for_thread("th1")
    assert codex.list_messages("th1") == []
    assert codex.get_external_thread_id("th1") is None


# --- engine selection --------------------------------------------------------

def test_build_codex_store_returns_sqlite_for_selfhost(tmp_path, monkeypatch):
    # Default self-host settings → sqlite engine → SqliteCodexStore.
    from src.platform_engines import settings as settings_mod
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    monkeypatch.delenv("PERSISTENCE_ENGINE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_mod.reset_settings_cache()
    store = build_codex_store(str(tmp_path / "state.db"))
    assert isinstance(store, SqliteCodexStore)
    settings_mod.reset_settings_cache()
