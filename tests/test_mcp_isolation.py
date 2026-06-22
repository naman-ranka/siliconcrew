"""MCP concurrency isolation — the env-race fix (Phase 2 I3).

The MCP server used to set ``os.environ["RTL_WORKSPACE"]`` per call; two
concurrent remote clients would clobber that global and write into each other's
workspace. The fix routes every tool call through ``run_in_session`` which binds
the workspace task-locally **inside the worker thread**. This test drives many
concurrent tool calls (each its own session) through that exact path and asserts
no cross-workspace writes — without importing the LangChain-heavy mcp_server.
"""
import asyncio
import os

import pytest

from src.platform_engines.request_scope import run_in_session
from src.utils.session_context import LocalWorkspaceProvider
from src.utils.workspace import get_workspace_path


N = 16


def _fake_tool(arguments: dict) -> str:
    """Stand-in for a LangChain tool .invoke(args): resolves workspace via the seam."""
    ws = get_workspace_path()
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, arguments["filename"]), "w", encoding="utf-8") as f:
        f.write(arguments["body"])
    return ws


def test_concurrent_mcp_tool_calls_are_isolated(tmp_path):
    provider = LocalWorkspaceProvider(str(tmp_path))
    sessions = [f"sess_{i}" for i in range(N)]

    async def main():
        async def one(sid):
            return await run_in_session(
                sid,
                _fake_tool,
                {"filename": f"{sid}.v", "body": f"// {sid}\n"},
                user_id=sid,
                provider=provider,
            )

        return dict(zip(sessions, await asyncio.gather(*(one(s) for s in sessions))))

    resolved = asyncio.run(main())

    for sid in sessions:
        expected_ws = os.path.join(str(tmp_path), sid)
        # Each call resolved to its OWN session workspace.
        assert os.path.abspath(resolved[sid]) == os.path.abspath(expected_ws)
        # On disk: each workspace holds only its own session's file.
        assert os.listdir(expected_ws) == [f"{sid}.v"]


def test_run_in_session_propagates_user_and_tier(tmp_path):
    """The bound SessionContext carries user_id + tier for tenancy/quotas."""
    provider = LocalWorkspaceProvider(str(tmp_path))
    seen = {}

    def capture(_args):
        from src.utils.session_context import get_current_session

        ctx = get_current_session()
        seen["user_id"] = ctx.user_id
        seen["tier"] = ctx.tier
        seen["session_id"] = ctx.session_id
        return "ok"

    async def main():
        return await run_in_session(
            "sX", capture, {}, user_id="google_7", tier="user", provider=provider
        )

    assert asyncio.run(main()) == "ok"
    assert seen == {"user_id": "google_7", "tier": "user", "session_id": "sX"}
