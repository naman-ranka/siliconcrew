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

from contextlib import contextmanager
from typing import Iterator, Optional

from src.utils.session_context import SessionContext, session_scope


@contextmanager
def session_request_scope(
    session_id: str, user_id: Optional[str] = None, provider=None
) -> Iterator[str]:
    """Run a block as a fully-bound request for ``session_id``.

    Yields the resolved workspace path. Usage::

        with session_request_scope(session_id, user_id=uid) as workspace:
            run_simulation(...)   # tools resolve `workspace` task-locally
    """
    if provider is None:
        from src.platform_engines.workspace_provider import get_workspace_provider

        provider = get_workspace_provider()

    workspace = provider.workspace_for(session_id)
    with session_scope(SessionContext(session_id=session_id, workspace=workspace, user_id=user_id)):
        try:
            yield workspace
        finally:
            # Persist back to durable storage when the provider supports it
            # (cloud). Local provider has no sync() — nothing to do.
            sync = getattr(provider, "sync", None)
            if callable(sync):
                sync(session_id)
