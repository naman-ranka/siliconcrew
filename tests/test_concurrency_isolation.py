"""THE GATE — multi-tenant concurrency isolation (Phase 2, slice 1).

The README names this the non-negotiable release gate: concurrent sessions
running through the tool layer must never write into each other's workspace.

This test does not need a live LLM. It exercises the exact seam the agent relies
on — ``session_scope`` setting a task-local ``SessionContext`` that every tool
resolves through ``get_workspace_path()`` — and drives it through the same
dispatch primitives the agent uses to run sync tools inside async turns:

  * ``asyncio.to_thread`` (used by FastAPI handlers / action endpoints), and
  * ``contextvars.copy_context().run(...)`` over a thread pool, which is what
    ``langchain_core.runnables.config.run_in_executor`` does internally.

Each simulated session performs a *sequence* of tool calls (write → read →
write) with a real barrier so all sessions are inside their scope at the same
instant — the precise condition under which a process-global workspace (the old
``os.environ['RTL_WORKSPACE']`` mutation) would corrupt across tenants.

The assertion is twofold:
  1. every tool call resolved to its own session's workspace (no cross-talk), and
  2. on disk, each workspace contains ONLY files written by its own session.
"""
import asyncio
import contextvars
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.utils.session_context import SessionContext, session_scope
from src.utils.workspace import get_workspace_path


N_SESSIONS = 12
N_TOOL_CALLS = 6


def _tool_write(filename: str, content: str) -> str:
    """Stand-in for wrappers.write_file: resolves workspace via the seam."""
    workspace = get_workspace_path()
    os.makedirs(workspace, exist_ok=True)
    with open(os.path.join(workspace, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return workspace


def _tool_list() -> set[str]:
    """Stand-in for list_files_tool."""
    workspace = get_workspace_path()
    return set(os.listdir(workspace)) if os.path.isdir(workspace) else set()


def _run_session_sequence(session_id: str, workspace: str, barrier: threading.Barrier) -> dict:
    """A session's full lifecycle: bind context, run a tool sequence, observe."""
    resolved = []
    with session_scope(SessionContext(session_id=session_id, workspace=workspace, user_id=session_id)):
        barrier.wait()  # every session is now simultaneously inside its own scope
        for i in range(N_TOOL_CALLS):
            resolved.append(_tool_write(f"{session_id}_file_{i}.v", f"// {session_id}\n"))
        listing = _tool_list()
    return {"resolved": resolved, "listing": listing}


def test_concurrent_threads_no_cross_workspace_writes(tmp_path):
    """Threaded dispatch (each session a thread) stays isolated end to end."""
    barrier = threading.Barrier(N_SESSIONS)
    sessions = {f"sess_{i}": str(tmp_path / f"sess_{i}") for i in range(N_SESSIONS)}
    results: dict[str, dict] = {}

    def worker(sid, ws):
        results[sid] = _run_session_sequence(sid, ws, barrier)

    threads = [threading.Thread(target=worker, args=(sid, ws)) for sid, ws in sessions.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    _assert_isolation(sessions, results)


def test_concurrent_async_tasks_through_executors(tmp_path):
    """asyncio tasks dispatching tool work to threads stay isolated.

    Mirrors the agent runtime: an async turn runs sync tools either via
    asyncio.to_thread or via copy_context().run on a pool. Both must preserve
    the per-task SessionContext.
    """
    sessions = {f"sess_{i}": str(tmp_path / f"sess_{i}") for i in range(N_SESSIONS)}
    pool = ThreadPoolExecutor(max_workers=N_SESSIONS)

    async def session_task(sid: str, ws: str, barrier: asyncio.Barrier) -> dict:
        # Bind the context in THIS task, then dispatch the tool sequence to a
        # worker thread the way LangChain runs sync tools: copy the context so
        # the contextvar propagates across the thread boundary.
        with session_scope(SessionContext(session_id=sid, workspace=ws, user_id=sid)):
            # Rendezvous so every session is concurrently inside its own scope
            # (asyncio.Barrier avoids starving the thread pool — the condition
            # under which a process-global workspace would corrupt across tenants).
            await barrier.wait()
            loop = asyncio.get_running_loop()
            resolved = []
            # (a) asyncio.to_thread path — copies context automatically.
            for i in range(N_TOOL_CALLS // 2):
                resolved.append(await asyncio.to_thread(_tool_write, f"{sid}_file_{i}.v", f"// {sid}\n"))
            # (b) run_in_executor with an explicit copied context (LangChain's path).
            for i in range(N_TOOL_CALLS // 2, N_TOOL_CALLS):
                ctx = contextvars.copy_context()
                resolved.append(
                    await loop.run_in_executor(
                        pool, lambda i=i, ctx=ctx: ctx.run(_tool_write, f"{sid}_file_{i}.v", f"// {sid}\n")
                    )
                )
            listing = await asyncio.to_thread(lambda ctx=contextvars.copy_context(): ctx.run(_tool_list))
            return {"resolved": resolved, "listing": listing}

    async def main():
        barrier = asyncio.Barrier(N_SESSIONS)
        tasks = [asyncio.create_task(session_task(sid, ws, barrier)) for sid, ws in sessions.items()]
        gathered = await asyncio.gather(*tasks)
        return dict(zip(sessions.keys(), gathered))

    results = asyncio.run(main())
    pool.shutdown(wait=True)
    _assert_isolation(sessions, results)


def test_bare_run_in_executor_without_copy_leaks(tmp_path):
    """Guardrail/regression: a BARE loop.run_in_executor does NOT copy context.

    This documents the one known footgun (called out in the Phase 0 README): if
    future code dispatches tools via a bare executor, the SessionContext does not
    propagate and the worker falls back to env/default. We assert that the
    *copied-context* path fixes it. This is a contract test for the seam, not an
    aspirational claim that bare dispatch is safe.
    """
    target = str(tmp_path / "real_session")

    async def main():
        loop = asyncio.get_running_loop()
        with session_scope(SessionContext("real_session", target, user_id="u")):
            with ThreadPoolExecutor(max_workers=1) as pool:
                bare = await loop.run_in_executor(pool, get_workspace_path)
                ctx = contextvars.copy_context()
                copied = await loop.run_in_executor(pool, lambda: ctx.run(get_workspace_path))
        return bare, copied

    bare, copied = asyncio.run(main())
    # The copied-context path correctly sees the session workspace...
    assert copied == os.path.abspath(target)
    # ...while the bare path leaks to the fallback (proving the copy is required).
    assert bare != os.path.abspath(target)


def _assert_isolation(sessions: dict[str, str], results: dict[str, dict]) -> None:
    # 1. Every tool call resolved to its own session's workspace.
    for sid, ws in sessions.items():
        expected = os.path.abspath(ws)
        resolved = results[sid]["resolved"]
        assert all(r == expected for r in resolved), (
            f"{sid}: a tool resolved to a foreign workspace: {set(resolved) - {expected}}"
        )
        # 2. The in-scope listing saw only this session's own files.
        assert results[sid]["listing"] == {f"{sid}_file_{i}.v" for i in range(N_TOOL_CALLS)}

    # 3. On disk, every workspace contains ONLY its own session's files.
    for sid, ws in sessions.items():
        on_disk = set(os.listdir(ws))
        assert on_disk == {f"{sid}_file_{i}.v" for i in range(N_TOOL_CALLS)}, (
            f"{sid}: cross-tenant file leak on disk: {on_disk}"
        )
