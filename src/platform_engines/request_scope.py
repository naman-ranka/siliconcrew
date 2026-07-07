"""Request lifecycle binding — the one place a request enters a session scope.

Every request (WebSocket chat turn, action endpoint) runs inside exactly one of
these. It ties together the Phase 0 tenancy seam and the Phase 2 workspace
provider:

  1. materialize the session workspace via the active ``WorkspaceProvider``
     (local dir, or cloud object-storage staged to local scratch);
  2. bind the task-local ``SessionContext`` so every tool resolves that workspace
     (no process-global env mutation);
  3. on exit, ``sync`` the workspace back to durable storage in cloud mode.

Local/self-host behavior is identical to today: the local provider returns the
same ``workspace/<session_id>`` path the session manager uses, and ``sync`` is a
no-op.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from src.utils.session_context import SessionContext, session_scope


@contextmanager
def session_request_scope(
    session_id: str, user_id: Optional[str] = None, provider=None, tier: Optional[str] = None,
    sync: bool = True,
) -> Iterator[str]:
    """Run a block as a fully-bound request for ``session_id``.

    Yields the resolved workspace path. Usage::

        with session_request_scope(session_id, user_id=uid) as workspace:
            run_simulation(...)   # tools resolve `workspace` task-locally

    ``sync`` (cloud only): whether to persist the workspace back to durable
    storage on exit. Pass ``sync=False`` for a read-only call so it doesn't
    re-tar+upload the whole workspace for nothing — the F2 latency fix, and the
    same policy the REST action router already applies (see actions.py
    ``run_scoped(mutates=…)``). A write-only durable channel that bypasses the
    workspace tarball (e.g. the synthesis run-store push) is unaffected either
    way. Self-host has no ``sync()`` so this is a no-op regardless.
    """
    if provider is None:
        from src.platform_engines.workspace_provider import get_workspace_provider

        provider = get_workspace_provider()

    workspace = provider.workspace_for(session_id)
    with session_scope(SessionContext(
        session_id=session_id, workspace=workspace, user_id=user_id, tier=tier,
    )):
        try:
            yield workspace
        finally:
            # Persist back to durable storage when the provider supports it
            # (cloud) AND this was a mutating call. Local provider has no sync()
            # — nothing to do. A read-only call skips the upload; anything it
            # appended (e.g. the activity log) rides the next mutating call's
            # sync (flush-on-next-mutation).
            if sync:
                sync_fn = getattr(provider, "sync", None)
                if callable(sync_fn):
                    sync_fn(session_id)


async def run_in_session(
    session_id: str,
    fn: Callable[..., Any],
    *args,
    user_id: Optional[str] = None,
    tier: Optional[str] = None,
    provider=None,
    sync: bool = True,
    **kwargs,
) -> Any:
    """Run a sync callable inside a fully-bound session scope, off the event loop.

    The scope is entered **inside the worker thread** so the task-local
    ``SessionContext`` is set in the same context the callable runs in — the
    correct way to propagate the seam across a thread boundary (a bare
    ``run_in_executor`` would NOT carry the contextvar). This is what replaces
    the MCP server's per-call ``os.environ["RTL_WORKSPACE"]`` mutation: each tool
    invocation resolves its workspace from this scope, so concurrent MCP clients
    are isolated with no shared process-global state.

    ``sync`` gates the cloud workspace write-back on exit (see
    ``session_request_scope``): the MCP server passes ``sync=False`` for
    read-only tools so a read never re-tars+uploads the whole workspace.
    """
    loop = asyncio.get_event_loop()

    def _invoke():
        with session_request_scope(session_id, user_id=user_id, tier=tier, provider=provider, sync=sync):
            return fn(*args, **kwargs)

    return await loop.run_in_executor(None, _invoke)
