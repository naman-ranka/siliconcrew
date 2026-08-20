"""F2: MCP workspace sync is gated to MUTATING tools.

Every MCP tool call used to re-tar+upload the whole workspace to object storage
on exit (``session_request_scope``'s ``finally`` → ``provider.sync``), even for
read-only tools — the primary "codex tool calls are slow" cause. The fix threads
a ``sync`` flag through ``run_in_session``/``session_request_scope`` and the MCP
server passes ``sync=(name in MUTATING_TOOLS)``.

These tests pin the mechanism (read → no sync, write → sync) and the policy set
(every workspace-writing tool is in MUTATING_TOOLS, so gating never silently
drops a writer's output). They fail on pre-fix code: ``run_in_session`` had no
``sync`` kwarg, so ``sync=False`` raises ``TypeError``.
"""
import asyncio
import os

from src.platform_engines.request_scope import run_in_session
from src.api.tool_catalog import MUTATING_TOOLS


class _RecordingProvider:
    """Local workspace provider that also records every sync() call."""

    def __init__(self, base):
        self._base = base
        self.synced = []

    def workspace_for(self, session_id):
        ws = os.path.join(self._base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    def sync(self, session_id):
        self.synced.append(session_id)


def test_read_only_call_does_not_sync(tmp_path):
    """A read-only tool call (sync=False) must NOT trigger a workspace upload."""
    provider = _RecordingProvider(str(tmp_path))

    async def main():
        return await run_in_session(
            "sess_read", lambda _a: "ok", {}, user_id="u1",
            provider=provider, sync=False,
        )

    assert asyncio.run(main()) == "ok"
    assert provider.synced == []  # no upload for a read


def test_mutating_call_syncs(tmp_path):
    """A mutating tool call (sync=True, the default) uploads exactly once."""
    provider = _RecordingProvider(str(tmp_path))

    async def main():
        return await run_in_session(
            "sess_write", lambda _a: "ok", {}, user_id="u1",
            provider=provider,  # sync defaults to True
        )

    assert asyncio.run(main()) == "ok"
    assert provider.synced == ["sess_write"]  # uploaded once


def test_sync_policy_covers_the_live_registry():
    """The MCP server's gate is exactly ``name in MUTATING_TOOLS``, so the
    policy has to stay in step with the registry.

    This used to re-type 37 of the 39 tool names by hand — a hand-written list
    guarding against hand-written lists, and it had already drifted (it never
    learned about ``build_interactive_sim`` or ``run_python_analysis``, so a
    writer could have been added with no MUTATING membership and the guard
    would have said nothing). Derive it instead:

      * every live tool is CLASSIFIED by the catalog, so a new tool cannot land
        without someone deciding its category — and its sync behaviour with it;
      * every name the policy mentions is a live tool, so a rename that misses
        the catalog fails here instead of silently dropping a tool's policy.

    Dead tool-name references anywhere else in the repo (docs, prompts,
    frontend, MCP) are covered by ``tests/test_tool_name_drift.py``; that the
    policy EXISTS at all, on the tool itself, is covered by
    ``tests/test_tool_policy.py``.
    """
    from src.tools.wrappers import ALL_TOOLS
    from src.api.tool_catalog import (
        ASYNC_TOOLS, EXCLUDED_FROM_UI, PROTECTED_TOOLS, TOOL_CATEGORIES,
    )

    # The whole registry, not just the MCP surface: policy now covers the
    # agent-only tools too (sleep_tool had none precisely because it was not
    # here), so scoping this to mcp_tools would report them as dead names.
    live = {t.name for t in ALL_TOOLS}
    classified = {name for names in TOOL_CATEGORIES.values() for name in names}

    unclassified = live - classified
    assert not unclassified, (
        "tools in the registry with no catalog category — nobody decided their "
        f"policy (categories, sign-in, sync): {sorted(unclassified)}"
    )

    for label, policy in (
        ("TOOL_CATEGORIES", classified),
        ("MUTATING_TOOLS", set(MUTATING_TOOLS)),
        ("PROTECTED_TOOLS", set(PROTECTED_TOOLS)),
        ("ASYNC_TOOLS", set(ASYNC_TOOLS)),
        ("EXCLUDED_FROM_UI", set(EXCLUDED_FROM_UI)),
    ):
        dead = policy - live
        assert not dead, f"{label} names no live tool answers to: {sorted(dead)}"


# --- 4B (hosted-latency plan): the bound Codex subprocess defers its per-tool
# sync to the parent's turn-end background sync ------------------------------


def _mcp_server_with_session(tmp_path, monkeypatch):
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    import mcp_server as mcp_mod

    from src.utils.session_manager import SessionManager
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "data" / "state.db"))
    sid = mgr.create_session("designA", user_id=None)
    return mcp_mod, sid


def _call_write_file(mcp_mod, server, monkeypatch):
    recorded = {}

    async def fake_run_in_session(session_id, fn, *args, sync=True, **kwargs):
        recorded["sync"] = sync
        return "ok"

    monkeypatch.setattr(mcp_mod, "run_in_session", fake_run_in_session)
    out = asyncio.run(server.call_tool("write_file", {"filename": "a.v", "content": "x"}))
    assert "ok" in " ".join(getattr(r, "text", "") for r in out)
    return recorded


def test_bound_codex_server_defers_per_tool_sync(tmp_path, monkeypatch):
    """When the parent owns the turn-end sync (the Codex engine sets
    SILICONCREW_MCP_DEFER_WORKSPACE_SYNC=1 for the bound subprocess it spawns),
    even a MUTATING tool call runs with sync=False — a tool result must not
    block on a full-workspace upload."""
    monkeypatch.setenv("SILICONCREW_MCP_DEFER_WORKSPACE_SYNC", "1")
    mcp_mod, sid = _mcp_server_with_session(tmp_path, monkeypatch)
    server = mcp_mod.RTLDesignMCPServer(codex_tools=True, bound_session=sid)
    assert server.defer_workspace_sync is True

    recorded = _call_write_file(mcp_mod, server, monkeypatch)
    assert recorded["sync"] is False, (
        "mutating call must defer the workspace upload to the parent's turn-end sync"
    )


def test_unflagged_server_still_syncs_mutating_tools(tmp_path, monkeypatch):
    """Without the defer flag (any non-Codex MCP client) the mutating-tool sync
    stays exactly as before — gating it off would silently lose writes."""
    monkeypatch.delenv("SILICONCREW_MCP_DEFER_WORKSPACE_SYNC", raising=False)
    mcp_mod, sid = _mcp_server_with_session(tmp_path, monkeypatch)
    server = mcp_mod.RTLDesignMCPServer(codex_tools=True, bound_session=sid)
    assert server.defer_workspace_sync is False

    recorded = _call_write_file(mcp_mod, server, monkeypatch)
    assert recorded["sync"] is True
