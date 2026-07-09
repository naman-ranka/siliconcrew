"""TTFT 3B/3C API seam: thread runtime prewarm + status endpoints.

Generic by design: the shell asks the thread's registered runtime IF it
exposes prewarm/worker_state — native threads (or absent capability) report
"unavailable" and the UI shows nothing. Owner scoping mirrors every other
thread route.
"""
import types

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient

import api
from src.agents import runtime_registry as rr


class _FakeWarmRuntime:
    def __init__(self):
        self.prewarm_calls = []
        self.state = "cold"

    async def run_turn(self, ctx):  # pragma: no cover - not driven here
        pass

    def worker_state(self, *, session_id, thread_id, user_id):
        return self.state

    async def prewarm(self, *, session_id, thread_id, user_id, workspace,
                      tier=None, auth_token=None, thread_row=None):
        self.prewarm_calls.append(
            dict(session_id=session_id, thread_id=thread_id, user_id=user_id,
                 workspace=workspace, auth_token=auth_token))
        self.state = "starting"
        return "starting"


@pytest.fixture
def warm_rt(monkeypatch, tmp_path):
    rr.clear_extensions()
    rt = _FakeWarmRuntime()
    rr.register_runtime(rr.RuntimeDescriptor(id="fake_warm", display_name="W"), rt)

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: sid == "sess1")
    monkeypatch.setattr(sm, "thread_belongs_to_session",
                        lambda tid, sid, user_id=None: tid == "th1" and sid == "sess1")
    monkeypatch.setattr(sm, "get_thread", lambda tid, user_id=None: {"runtime": "fake_warm", "session_id": "sess1"})

    class _WS:
        def workspace_for(self, sid):
            d = tmp_path / sid
            d.mkdir(parents=True, exist_ok=True)
            return str(d)

    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    yield rt
    rr.clear_extensions()


def test_prewarm_dispatches_to_the_threads_runtime(warm_rt):
    c = TestClient(api.app)
    r = c.post("/api/sessions/sess1/threads/th1/runtime/prewarm")
    assert r.status_code == 200
    assert r.json() == {"state": "starting"}
    assert len(warm_rt.prewarm_calls) == 1
    call = warm_rt.prewarm_calls[0]
    assert call["session_id"] == "sess1" and call["thread_id"] == "th1"
    assert call["workspace"].endswith("sess1")

    # Status reflects the runtime's honest state.
    s = c.get("/api/sessions/sess1/threads/th1/runtime/status")
    assert s.json() == {"state": "starting"}


def test_unknown_thread_404s(warm_rt):
    c = TestClient(api.app)
    assert c.post("/api/sessions/sess1/threads/nope/runtime/prewarm").status_code == 404
    assert c.get("/api/sessions/sess1/threads/nope/runtime/status").status_code == 404


def test_native_thread_reports_unavailable(monkeypatch, warm_rt):
    """A thread on the native runtime (no warm capability) is honest: no fake
    setup state, no spawn."""
    sm = api.session_manager
    monkeypatch.setattr(sm, "get_thread", lambda tid, user_id=None: {"runtime": "langchain", "session_id": "sess1"})
    c = TestClient(api.app)
    assert c.post("/api/sessions/sess1/threads/th1/runtime/prewarm").json() == {"state": "unavailable"}
    assert c.get("/api/sessions/sess1/threads/th1/runtime/status").json() == {"state": "unavailable"}
    assert warm_rt.prewarm_calls == []
