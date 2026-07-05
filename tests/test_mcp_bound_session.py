"""Bound-session MCP isolation (Phase 3) — the Codex tool boundary.

A Codex-launched MCP server is locked to one session: it verifies ownership on
construction, refuses session-management tools, and refuses any tool aimed at a
different session. (Exercised for real only when the Codex subprocess runs it;
these prove the guard logic without the SDK.)
"""
import asyncio
import os

import pytest


@pytest.fixture
def bound_server(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    # Fresh import so the server binds to the temp data dir.
    import importlib
    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    # Create a session the local identity owns, then bind to it.
    from src.utils.session_manager import SessionManager
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "data" / "state.db"))
    sid = mgr.create_session("designA", user_id=None)

    server = mcp_mod.RTLDesignMCPServer(codex_tools=True, bound_session=sid)
    return server, sid, mcp_mod


def _text(results):
    return " ".join(getattr(r, "text", "") for r in results)


def test_bound_server_pins_current_session(bound_server):
    server, sid, _ = bound_server
    assert server.bound_session == sid
    assert server.current_session == sid


def test_session_management_tools_blocked(bound_server):
    server, sid, _ = bound_server
    for tool in ("create_session_tool", "list_sessions_tool", "delete_session_tool", "set_active_session"):
        out = asyncio.run(server.call_tool(tool, {"session_name": "x", "session_id": sid}))
        assert "disabled" in _text(out).lower()


def test_cross_session_access_denied(bound_server):
    server, sid, _ = bound_server
    out = asyncio.run(server.call_tool("get_manifest", {"session_id": "someone-elses-session"}))
    assert "access denied" in _text(out).lower()


def test_bound_resources_scoped_to_bound_session(tmp_path, monkeypatch):
    """The RESOURCE surface must respect the bound session too: a bound server
    may not enumerate or read another session's resources (regression for the
    tool-bound-but-resource-unbound leak)."""
    from urllib.parse import quote

    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    import importlib
    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    from src.utils.session_manager import SessionManager
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "data" / "state.db"))
    sid_a = mgr.create_session("designA", user_id=None)
    sid_b = mgr.create_session("designB", user_id=None)
    with open(os.path.join(mgr.get_workspace_path(sid_b), "secret.v"), "w") as f:
        f.write("module secret; endmodule")

    server = mcp_mod.RTLDesignMCPServer(codex_tools=True, bound_session=sid_a)

    # list_resources exposes only the bound session, never designB.
    uris = " ".join(str(r.uri) for r in asyncio.run(server.list_resources()))
    assert sid_a in uris and sid_b not in uris

    # read_resource across the boundary is denied (file AND metadata).
    with pytest.raises(ValueError):
        asyncio.run(server.read_resource(f"rtl://session/{quote(sid_b, safe='')}/file/secret.v"))
    with pytest.raises(ValueError):
        asyncio.run(server.read_resource(f"rtl://session/{quote(sid_b, safe='')}"))

    # The bound session's own resource still reads.
    asyncio.run(server.read_resource(f"rtl://session/{quote(sid_a, safe='')}"))


def test_construction_refuses_unowned_session(tmp_path, monkeypatch):
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import importlib
    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)
    with pytest.raises(RuntimeError):
        mcp_mod.RTLDesignMCPServer(bound_session="never-created-session")
