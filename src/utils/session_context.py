"""Per-request session / workspace context — the Phase 0 tenancy seam.

Why this exists
---------------
Tools must resolve *which workspace they act on* from an explicit, task-local
context — never from process-global state. The original backend did::

    os.environ["RTL_WORKSPACE"] = workspace   # per incoming request

and every tool read that global via ``get_workspace_path()``. In a single local
user that is fine. Under the deployed UI a single process serves many users
concurrently, so two requests race on the global: user A's tools can end up
writing into user B's workspace. That is cross-tenant corruption, and it is the
prerequisite blocker for multi-tenant deployment.

The served request lifecycle no longer mutates that env var: ``api.py`` binds
each connection's task to a ``SessionContext`` (``set_current_session`` /
``session_scope``) and ``get_workspace_path()`` resolves it task-locally. The
``RTL_WORKSPACE`` env var remains only as a read-only single-tenant override.
Isolation under concurrency is the release gate
(``tests/test_concurrency_isolation.py``).

Design
------
* ``SessionContext`` carries the identity of the current request.
* It lives in a ``contextvars.ContextVar``, which is *task-local*: concurrent
  asyncio tasks and threads each see their own value, with no cross-talk.
* ``get_workspace_path()`` prefers this context, then falls back to the
  ``RTL_WORKSPACE`` env var, then the default — so behavior is unchanged until
  a caller sets a context. This makes adoption incremental and safe.
* ``WorkspaceProvider`` abstracts *how* a workspace is materialized. Phase 1
  uses ``LocalWorkspaceProvider`` (a directory on disk). Phase 2 swaps in a
  cloud-backed provider (object storage staged to local scratch) behind the
  same interface — no tool or API change required.
"""
from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional, Protocol


@dataclass(frozen=True)
class SessionContext:
    """Identity of the request a tool is currently executing for."""

    session_id: str
    workspace: str
    user_id: Optional[str] = None  # Phase 2 tenancy / auth (None = self-host)
    tier: Optional[str] = None     # "user" | "anonymous"; quota policy selector


_current: contextvars.ContextVar[Optional[SessionContext]] = contextvars.ContextVar(
    "siliconcrew_session_ctx", default=None
)


def get_current_session() -> Optional[SessionContext]:
    """Return the active SessionContext for this task/thread, or None."""
    return _current.get()


def current_workspace() -> Optional[str]:
    """Workspace path for the active session, or None if unset."""
    ctx = _current.get()
    return ctx.workspace if ctx else None


def set_current_session(ctx: SessionContext) -> contextvars.Token:
    """Set the active session; returns a token to pass to reset."""
    return _current.set(ctx)


def reset_current_session(token: contextvars.Token) -> None:
    """Restore the previous session (pair with set_current_session)."""
    _current.reset(token)


@contextmanager
def session_scope(ctx: SessionContext) -> Iterator[SessionContext]:
    """Scope a block of work to a session context.

    Usage::

        with session_scope(SessionContext(session_id, workspace)):
            run_simulation(...)   # get_workspace_path() resolves to `workspace`
    """
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


class WorkspaceProvider(Protocol):
    """How a workspace path is materialized for a session.

    Implementations are swappable behind this interface so the tool layer never
    needs to know whether storage is local or cloud-backed.
    """

    def workspace_for(self, session_id: str) -> str:
        ...


@dataclass
class LocalWorkspaceProvider:
    """Workspaces are directories under ``base_dir`` (Phase 1 / local / self-host)."""

    base_dir: str

    def workspace_for(self, session_id: str) -> str:
        path = os.path.join(self.base_dir, session_id)
        os.makedirs(path, exist_ok=True)
        return path
