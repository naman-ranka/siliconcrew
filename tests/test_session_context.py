"""Phase 0 seam: session/workspace context must be task-local and isolated.

These tests prove the mechanism that replaces the process-global RTL_WORKSPACE
env var (the cross-tenant race). The core context tests use only stdlib so they
run without the heavy tool dependencies; the get_workspace_path integration
test skips cleanly if those deps are absent.
"""
import os
import threading

import pytest

from src.utils.session_context import (
    LocalWorkspaceProvider,
    SessionContext,
    current_workspace,
    session_scope,
)


def test_current_workspace_none_by_default():
    assert current_workspace() is None


def test_session_scope_sets_and_resets():
    with session_scope(SessionContext("s1", "/ws/s1")):
        assert current_workspace() == "/ws/s1"
    assert current_workspace() is None  # restored on exit


def test_concurrent_threads_are_isolated():
    """Two threads inside their own scopes simultaneously must not cross-talk."""
    results = {}
    barrier = threading.Barrier(2)

    def worker(name):
        with session_scope(SessionContext(name, f"/ws/{name}")):
            barrier.wait()  # ensure both are inside their scope at the same time
            results[name] = current_workspace()

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == {"a": "/ws/a", "b": "/ws/b"}


def test_local_provider_creates_workspace_dir(tmp_path):
    provider = LocalWorkspaceProvider(str(tmp_path))
    path = provider.workspace_for("sess1")
    assert os.path.isdir(path)
    assert path == os.path.join(str(tmp_path), "sess1")


def test_get_workspace_path_prefers_context(tmp_path):
    wrappers = pytest.importorskip("src.tools.wrappers")
    # No context: falls back to env/default (legacy behavior preserved).
    assert wrappers.get_workspace_path()  # does not raise
    # With context: resolves to the session workspace.
    with session_scope(SessionContext("s1", str(tmp_path))):
        assert wrappers.get_workspace_path() == os.path.abspath(str(tmp_path))
    # After scope: context no longer influences resolution.
    assert wrappers.get_workspace_path() != os.path.abspath(str(tmp_path)) or \
        os.environ.get("RTL_WORKSPACE") == str(tmp_path)
