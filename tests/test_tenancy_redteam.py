"""RED-TEAM: cross-tenant access must fail (Phase 2 schema tenancy, release gate).

User A, holding a valid identity, must never read, list, mutate, or delete user
B's session or workspace. These tests exercise the MetadataStore tenant filter
and the SessionManager that threads ``user_id`` through it. If any assertion
fails, multi-tenant isolation is broken and the build should fail.

No LangChain / heavy deps — pure store + session-manager + filesystem.
"""
import datetime
import shutil

import pytest

from src.platform_engines.metadata_store import SqliteMetadataStore
from src.platform_engines.settings import reset_settings_cache
from src.utils.session_manager import SessionManager


# --------------------------------------------------------------------------
# Store-level tenant filtering
# --------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "state.db"))
    s.init_schema()
    now = datetime.datetime.now()
    s.upsert_session("alice_sess", "alice", "Alice's design", "m", None, now)
    s.upsert_session("bob_sess", "bob", "Bob's design", "m", None, now)
    return s


def test_get_session_is_tenant_scoped(store):
    # Owner can read their own session.
    assert store.get_session("alice_sess", user_id="alice")["session_name"] == "Alice's design"
    # A valid OTHER user gets nothing for a session they don't own (the gate).
    assert store.get_session("bob_sess", user_id="alice") is None
    assert store.get_session("alice_sess", user_id="bob") is None


def test_list_is_tenant_scoped(store):
    alice_ids = {r["session_id"] for r in store.get_all_session_rows(user_id="alice")}
    assert alice_ids == {"alice_sess"}
    bob_ids = {r["session_id"] for r in store.get_all_session_rows(user_id="bob")}
    assert bob_ids == {"bob_sess"}


def test_cross_tenant_delete_is_noop(store):
    store.delete_session("bob_sess", user_id="alice")  # A tries to delete B's row
    # B's row survives untouched.
    assert store.get_session("bob_sess", user_id="bob") is not None


def test_cross_tenant_move_is_noop(store):
    store.move_session("bob_sess", "some_project", user_id="alice")
    assert store.get_session("bob_sess", user_id="bob")["project_id"] is None


def test_owner_is_immutable_on_upsert(store):
    now = datetime.datetime.now()
    # An attacker re-upserts B's session id claiming ownership; owner must not change.
    store.upsert_session("bob_sess", "alice", "hijack", "m", None, now)
    assert store.get_session("bob_sess", user_id="alice") is None
    assert store.get_session("bob_sess", user_id="bob") is not None


def test_legacy_null_owner_rows_invisible_to_tenants(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "legacy.db"))
    s.init_schema()
    now = datetime.datetime.now()
    s.upsert_session("legacy_sess", None, "legacy", "m", None, now)  # unowned legacy row
    # Self-host (unscoped) still sees it.
    assert s.get_session("legacy_sess", user_id=None) is not None
    # No real tenant can.
    assert s.get_session("legacy_sess", user_id="alice") is None


# --------------------------------------------------------------------------
# SessionManager-level isolation (incl. the workspace filesystem)
# --------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"))


def test_session_manager_cross_tenant_read_returns_none(manager):
    manager.create_session("design", user_id="alice")
    assert manager.get_session_metadata("design", user_id="alice") is not None
    # Bob, with a valid identity, sees nothing for Alice's session.
    assert manager.get_session_metadata("design", user_id="bob") is None
    assert manager.owns_session("design", "bob") is False
    assert manager.owns_session("design", "alice") is True


def test_session_manager_list_isolation(manager):
    manager.create_session("a1", user_id="alice")
    manager.create_session("b1", user_id="bob")
    assert manager.get_all_sessions(user_id="alice") == ["a1"]
    assert manager.get_all_sessions(user_id="bob") == ["b1"]


def test_session_manager_cross_tenant_delete_blocked(manager, tmp_path):
    manager.create_session("secret", user_id="alice")
    workspace = manager.get_workspace_path("secret")
    import os

    assert os.path.isdir(workspace)
    # Bob attempts to delete Alice's session/workspace -> blocked, files intact.
    with pytest.raises(PermissionError):
        manager.delete_session("secret", user_id="bob")
    assert os.path.isdir(workspace)
    # Alice can delete her own.
    manager.delete_session("secret", user_id="alice")
    assert not os.path.isdir(workspace)


def test_self_host_unscoped_still_works(manager):
    """user_id=None (self-host) keeps today's behavior: any session is visible."""
    manager.create_session("local_design", user_id=None)
    assert manager.get_session_metadata("local_design") is not None
    assert manager.get_all_sessions() == ["local_design"]
    assert manager.owns_session("local_design", None) is True


def test_hosted_session_list_uses_metadata_when_workspace_dir_is_ephemeral(tmp_path, monkeypatch):
    """Hosted session lists must survive Cloud Run local-disk loss.

    In hosted mode the metadata store is durable and workspaces are rehydrated
    through WorkspaceProvider. The local scratch directory is not a reliable
    source of truth for whether a session exists.
    """
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    try:
        manager = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"))
        manager.create_session("cloud_design", user_id="alice")
        shutil.rmtree(manager.get_workspace_path("cloud_design"))

        assert manager.get_all_sessions(user_id="alice") == ["cloud_design"]
    finally:
        reset_settings_cache()
