"""Workspace path resolution — the dependency-light core of the tenancy seam.

This module deliberately has **no** heavy imports (no LangChain, no tools). It is
the single function every tool funnels through to learn *which workspace it acts
on*, so it must be importable in isolation — by the FastAPI request lifecycle,
by background job workers, and by the concurrency-isolation gate test — without
dragging in the agent/tool dependency tree.

Resolution order (the Phase 0 tenancy seam):

  1. task-local ``SessionContext``  (multi-tenant safe; set per request)
  2. ``RTL_WORKSPACE`` env var       (legacy / single-tenant self-host override)
  3. ``workspace/`` relative to the project root (default)

The context (1) is what makes concurrent multi-user requests safe: it is a
``contextvars.ContextVar``, so each asyncio task / thread sees its own value with
no cross-talk. The env var (2) is preserved only as a single-tenant override and
is **never mutated per request** — mutating a process-global per request is the
exact race this seam exists to eliminate.
"""
from __future__ import annotations

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_WORKSPACE = os.path.join(_PROJECT_ROOT, "workspace")


def get_workspace_path() -> str:
    """Return the absolute path of the workspace the current request acts on.

    See module docstring for the resolution order. Importing
    :mod:`src.utils.session_context` lazily keeps this function usable even in
    minimal environments, but that module is itself dependency-light.
    """
    # 1. Prefer the task-local session context when one is active. This is what
    #    makes concurrent multi-user requests safe; see utils.session_context.
    try:
        from src.utils.session_context import current_workspace

        ctx_ws = current_workspace()
        if ctx_ws:
            return os.path.abspath(ctx_ws)
    except Exception:
        pass

    # 2. Legacy single-tenant override. Read-only here — never written per request.
    env_path = os.environ.get("RTL_WORKSPACE")
    if env_path:
        return os.path.abspath(env_path)

    # 3. Default project-local workspace.
    return os.path.abspath(_DEFAULT_WORKSPACE)
