"""naman-ranka/siliconcrew#77 — get_prompt must honor the bound-session guard.

The guard lived only in ``call_tool``: a ``prompts/get`` arriving at a BOUND
server (the Codex engine spawns one per turn, locked to exactly one session)
with no ``session_id`` ran ``ensure_session`` unconditionally — minting a fresh
``mcp_session_<ts>`` — and then wrote it to the process-global active-session
pointer, clobbering the bind. An explicit different session_id was equally
accepted. Pre-fix, the first three tests below fail.

Drives the real server object directly (``asyncio.run``, no live transport),
same pattern as tests/test_mcp_workspace_paths.py — none of the env deps of the
excluded test_mcp.py.
"""
import asyncio
import importlib

import pytest


@pytest.fixture
def mcp_mod(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import mcp_server as mod

    importlib.reload(mod)
    return mod


@pytest.fixture
def bound(mcp_mod):
    """A session created up front + a second server instance BOUND to it —
    the exact shape the Codex engine spawns."""
    setup = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    asyncio.run(setup.call_tool("create_session_tool", {"session_name": "bound_target"}))
    sid = setup.current_session
    assert sid
    server = mcp_mod.RTLDesignMCPServer(codex_tools=False, bound_session=sid)
    return server, sid


def _prompt_text(result):
    return " ".join(getattr(m.content, "text", "") for m in result.messages)


def test_bound_get_prompt_without_session_uses_bound_session(bound):
    """No session_id on a bound server → the bound session, never a fresh
    ``mcp_session_<ts>``. Pre-fix this minted and activated a stray session."""
    server, sid = bound
    before = set(server.session_manager.get_all_sessions())

    result = asyncio.run(server.get_prompt("rtl_design_workflow", None))

    assert f"**CURRENT SESSION**: {sid}" in _prompt_text(result)
    # No stray session was created...
    assert set(server.session_manager.get_all_sessions()) == before
    # ...and the active-session pointer still holds the bind.
    assert server.current_session == sid


def test_bound_get_prompt_rejects_a_different_session(bound, mcp_mod):
    """An explicit mismatched session_id is refused, same semantics as
    call_tool. Pre-fix it was ensured, activated, and described in the prompt."""
    server, sid = bound
    other_setup = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    asyncio.run(other_setup.call_tool("create_session_tool", {"session_name": "other"}))
    other = other_setup.current_session
    assert other and other != sid

    with pytest.raises(ValueError, match="bound to session"):
        asyncio.run(server.get_prompt("rtl_design_workflow", {"session_id": other}))

    assert server.current_session == sid


def test_bound_get_prompt_never_ensures_a_nonexistent_session(bound):
    """Even a NEW name must not be materialized by a bound server — pre-fix
    ensure_session created and owned it."""
    server, sid = bound
    before = set(server.session_manager.get_all_sessions())

    with pytest.raises(ValueError, match="bound to session"):
        asyncio.run(server.get_prompt("rtl_design_workflow", {"session_id": "not_a_real_session"}))

    assert set(server.session_manager.get_all_sessions()) == before
    assert server.current_session == sid


def test_bound_get_prompt_accepts_the_matching_explicit_session(bound):
    server, sid = bound
    result = asyncio.run(server.get_prompt("rtl_design_workflow", {"session_id": sid}))
    assert f"**CURRENT SESSION**: {sid}" in _prompt_text(result)
    assert server.current_session == sid


def test_unbound_get_prompt_still_mints_a_session(mcp_mod):
    """No-regression leg: unbound behavior is unchanged — no session_id still
    creates and activates a fresh mcp_session_<ts>."""
    server = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    result = asyncio.run(server.get_prompt("rtl_design_workflow", None))
    assert "mcp_session_" in _prompt_text(result)
    assert server.current_session and server.current_session.startswith("mcp_session_")
