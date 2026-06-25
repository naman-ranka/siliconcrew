"""Propagation gate: the session context must survive into tool execution.

api.py binds each WebSocket connection's task to a SessionContext. Tools are
sync `@tool` functions that LangGraph runs from the async agent loop. These
tests prove the contextvar reaches the tool, both for the realistic LangChain
executor path and for concurrent tasks (the multi-user scenario).

If any of these fail, multi-tenant workspace isolation is NOT safe — treat it
as a release blocker, not a flake.
"""
import asyncio

import pytest

from src.utils.session_context import (
    SessionContext,
    current_workspace,
    session_scope,
)


def test_concurrent_async_tasks_are_isolated():
    """Two concurrent connections (tasks) must not see each other's workspace."""

    async def worker(name: str) -> str:
        with session_scope(SessionContext(name, f"/ws/{name}")):
            await asyncio.sleep(0.01)  # force interleaving
            return current_workspace()

    async def main():
        return await asyncio.gather(worker("a"), worker("b"))

    assert set(asyncio.run(main())) == {"/ws/a", "/ws/b"}


def test_propagates_through_context_copying_executor():
    """to_thread copies context — same mechanism LangChain uses for sync tools."""

    async def main():
        with session_scope(SessionContext("s1", "/ws/s1")):
            return await asyncio.to_thread(current_workspace)

    assert asyncio.run(main()) == "/ws/s1"


def test_propagates_through_langchain_run_in_executor():
    """The exact primitive LangChain uses to run sync tools in async contexts.

    `langchain_core.runnables.config.run_in_executor` copies the context, so a
    tool reading get_workspace_path()/current_workspace() sees this session.
    """
    config = pytest.importorskip("langchain_core.runnables.config")
    run_in_executor = config.run_in_executor

    async def main():
        with session_scope(SessionContext("s1", "/ws/s1")):
            return await run_in_executor(None, current_workspace)

    assert asyncio.run(main()) == "/ws/s1"
