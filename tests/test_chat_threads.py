"""Chat threads — CRUD, tenant isolation (red-team), back-compat (Task 1).

A chat = a LangGraph thread_id; the workspace = session_id. Many threads per
session, all sharing the LIVE workspace. These tests cover the store + the
SessionManager wrappers (no LangChain needed).
"""
import datetime

import pytest

from src.platform_engines.metadata_store import SqliteMetadataStore
from src.utils.session_manager import SessionManager


@pytest.fixture
def mgr(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"))


# --- back-compat: default thread is id == session_id ------------------------


def test_default_thread_is_session_id_chat_one(mgr):
    mgr.create_session("design", user_id="alice")
    threads = mgr.list_threads("design", user_id="alice")
    assert len(threads) == 1
    assert threads[0]["id"] == "design"          # zero-migration: id == session_id
    assert threads[0]["title"] == "Chat 1"


def test_legacy_session_exposes_history_as_chat_one(tmp_path):
    """A session that predates chat_threads gets a Chat 1 row on first list."""
    store = SqliteMetadataStore(str(tmp_path / "state.db"))
    store.init_schema()
    now = datetime.datetime.now()
    store.upsert_session("legacy", "alice", "Legacy", "m", None, now)  # no thread rows
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"),
                         metadata_store=store)
    import os
    os.makedirs(os.path.join(mgr.base_dir, "legacy"), exist_ok=True)
    threads = mgr.list_threads("legacy", user_id="alice")
    assert [t["id"] for t in threads] == ["legacy"]
    assert threads[0]["title"] == "Chat 1"


# --- CRUD -------------------------------------------------------------------


def test_create_lists_renames_deletes(mgr):
    mgr.create_session("s1", user_id="alice")
    t2 = mgr.create_thread("s1", user_id="alice")
    assert t2["id"] != "s1" and t2["title"] == "Chat 2"
    t3 = mgr.create_thread("s1", user_id="alice", title="Counter design")
    assert t3["title"] == "Counter design"

    ids = {t["id"] for t in mgr.list_threads("s1", user_id="alice")}
    assert ids == {"s1", t2["id"], t3["id"]}

    mgr.rename_thread(t2["id"], "Renamed", user_id="alice")
    assert mgr.get_thread(t2["id"], user_id="alice")["title"] == "Renamed"

    mgr.delete_thread(t2["id"], user_id="alice")
    ids = {t["id"] for t in mgr.list_threads("s1", user_id="alice")}
    assert t2["id"] not in ids and "s1" in ids


def test_list_newest_active_first(mgr):
    mgr.create_session("s1", user_id="alice")
    a = mgr.create_thread("s1", user_id="alice")
    b = mgr.create_thread("s1", user_id="alice")
    mgr.touch_thread(a["id"], user_id="alice")  # a is now most recently active
    order = [t["id"] for t in mgr.list_threads("s1", user_id="alice")]
    assert order[0] == a["id"]


def test_auto_title_from_first_message(mgr):
    mgr.create_session("s1", user_id="alice")
    t = mgr.create_thread("s1", user_id="alice")  # title "Chat 2"
    # First message auto-titles only when still default/untitled.
    mgr.rename_thread(t["id"], "Chat 1", user_id="alice")  # simulate default-ish
    mgr.touch_thread(t["id"], user_id="alice", auto_title_from="Build an 8-bit counter please")
    assert mgr.get_thread(t["id"], user_id="alice")["title"].startswith("Build an 8-bit counter")
    # A user-set title is preserved.
    mgr.rename_thread(t["id"], "My title", user_id="alice")
    mgr.touch_thread(t["id"], user_id="alice", auto_title_from="something else entirely")
    assert mgr.get_thread(t["id"], user_id="alice")["title"] == "My title"


# --- RED-TEAM: cross-tenant access must fail --------------------------------


def test_tenant_cannot_list_or_read_foreign_threads(mgr):
    mgr.create_session("alice_s", user_id="alice")
    mgr.create_session("bob_s", user_id="bob")
    a_thread = mgr.create_thread("alice_s", user_id="alice")

    # Bob lists Alice's session threads -> empty (scoped to bob).
    assert mgr.list_threads("alice_s", user_id="bob") == []
    # Bob reads Alice's thread by id -> None.
    assert mgr.get_thread(a_thread["id"], user_id="bob") is None
    # Owner still sees it.
    assert mgr.get_thread(a_thread["id"], user_id="alice") is not None


def test_tenant_cannot_delete_or_rename_foreign_threads(mgr):
    mgr.create_session("alice_s", user_id="alice")
    a_thread = mgr.create_thread("alice_s", user_id="alice")

    mgr.delete_thread(a_thread["id"], user_id="bob")    # no-op (scoped)
    assert mgr.get_thread(a_thread["id"], user_id="alice") is not None
    mgr.rename_thread(a_thread["id"], "hijacked", user_id="bob")  # no-op
    assert mgr.get_thread(a_thread["id"], user_id="alice")["title"] != "hijacked"


def test_thread_belongs_to_session_guard(mgr):
    mgr.create_session("s1", user_id="alice")
    mgr.create_session("s2", user_id="alice")
    t = mgr.create_thread("s1", user_id="alice")
    assert mgr.thread_belongs_to_session(t["id"], "s1", user_id="alice")
    # Same owner, wrong session -> rejected (prevents cross-session thread access).
    assert not mgr.thread_belongs_to_session(t["id"], "s2", user_id="alice")


def test_self_host_unscoped_threads(mgr):
    """user_id=None (self-host) still works and is unscoped."""
    mgr.create_session("local", user_id=None)
    t = mgr.create_thread("local", user_id=None)
    ids = {x["id"] for x in mgr.list_threads("local", user_id=None)}
    assert {"local", t["id"]} <= ids
