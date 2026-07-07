"""F1 regression — hosted MCP session tools must be tenant-scoped.

Three defects were confirmed on the hosted MCP session surface (see
plans/overnight-20260706/reports/F1-tenancy.md):

1. ``list_sessions_tool`` called ``get_all_sessions()`` with no ``user_id`` →
   every tenant's sessions leaked (the reported 33-session leak).
2. ``delete_session_tool`` called ``delete_session()`` with no ``user_id`` →
   the ownership guard was bypassed, so any signed-in user could rmtree ANY
   tenant's workspace/chats/checkpoints by id (single-request, destructive).
3. ``current_session`` is a process-global on the one shared hosted server, so
   a concurrent tenant can flip it underneath a caller; a pre-dispatch
   ``owns_session`` gate now rejects a workspace flipped out from under you.

These drive ``call_tool`` directly against an in-memory sqlite-backed
SessionManager with ``_hosted`` forced on and ``_scoped_user_id`` stubbed per
actor — no live Postgres, no SDK. Each asserts the POST-FIX behavior; every one
FAILS on pre-fix code (list returns both tenants, delete destroys B, the flipped
workspace dispatches).
"""
import asyncio
import os

import pytest


def _text(results):
    return " ".join(getattr(r, "text", "") for r in results)


@pytest.fixture
def hosted_server(tmp_path, monkeypatch):
    """A non-bound MCP server over a temp sqlite store, forced into hosted mode,
    seeded with two tenants (alice, bob). ``set_actor`` swaps the caller."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import importlib
    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    server = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    # Force the tenancy guards on without needing a real hosted (Postgres) boot.
    server._hosted = True

    # Seed two owners' sessions through the server's own manager.
    mgr = server.session_manager
    alice_sid = mgr.create_session("alice_design", user_id="alice")
    bob_sid = mgr.create_session("bob_design", user_id="bob")

    actor = {"uid": "alice"}
    server._scoped_user_id = lambda: actor["uid"]

    def set_actor(uid):
        actor["uid"] = uid

    return server, alice_sid, bob_sid, set_actor


def test_list_sessions_scoped_to_caller(hosted_server):
    server, alice_sid, bob_sid, set_actor = hosted_server
    set_actor("alice")
    out = _text(asyncio.run(server.call_tool("list_sessions_tool", {})))
    assert alice_sid in out
    # Pre-fix: bob's session leaks into alice's list.
    assert bob_sid not in out

    set_actor("bob")
    out = _text(asyncio.run(server.call_tool("list_sessions_tool", {})))
    assert bob_sid in out
    assert alice_sid not in out


def test_delete_session_cross_tenant_blocked(hosted_server):
    server, alice_sid, bob_sid, set_actor = hosted_server
    bob_ws = server.session_manager.get_workspace_path(bob_sid)
    assert os.path.isdir(bob_ws)

    set_actor("alice")  # alice tries to delete bob's session by id
    out = _text(asyncio.run(server.call_tool("delete_session_tool", {"session_id": bob_sid})))

    # Pre-fix: bob's workspace + metadata are destroyed. Post-fix: intact, and the
    # response must not confirm the session's existence.
    assert os.path.isdir(bob_ws)
    assert server.session_manager.owns_session(bob_sid, "bob") is True
    assert "not found" in out.lower()

    # Owner can still delete their own.
    set_actor("bob")
    out = _text(asyncio.run(server.call_tool("delete_session_tool", {"session_id": bob_sid})))
    assert "deleted" in out.lower()
    assert not os.path.isdir(bob_ws)


def test_flipped_active_session_rejected_before_dispatch(hosted_server):
    """Simulate root cause 3: a concurrent tenant flipped current_session to
    bob's session while alice is the caller. The pre-dispatch gate must refuse
    to touch bob's workspace instead of dispatching a read/write there."""
    server, alice_sid, bob_sid, set_actor = hosted_server
    server.current_session = bob_sid  # flipped underneath the caller
    set_actor("alice")

    out = _text(asyncio.run(server.call_tool("read_file", {"file_path": "anything.v"})))
    # Pre-fix: read_file dispatches against bob's workspace. Post-fix: rejected.
    assert "active session for this user" in out.lower()


def test_self_host_unscoped_unchanged(tmp_path, monkeypatch):
    """Self-host (uid None, not hosted) keeps today's behavior: list shows all
    sessions, delete works, and the pre-dispatch gate is a no-op."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import importlib
    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    server = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    assert server._hosted is False
    mgr = server.session_manager
    s1 = mgr.create_session("d1", user_id=None)
    s2 = mgr.create_session("d2", user_id=None)

    out = _text(asyncio.run(server.call_tool("list_sessions_tool", {})))
    assert s1 in out and s2 in out  # single-tenant sees everything

    s2_ws = mgr.get_workspace_path(s2)
    out = _text(asyncio.run(server.call_tool("delete_session_tool", {"session_id": s2})))
    assert "deleted" in out.lower()
    assert not os.path.isdir(s2_ws)
