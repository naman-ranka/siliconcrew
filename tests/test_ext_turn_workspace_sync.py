"""4B (hosted-latency plan): an extension (Codex) turn persists the workspace
ONCE per turn, in the background — the native path's proven cadence.

Before the fix the extension branch in the chat WS handler ``continue``d past
the native path's turn-end background sync, so Codex durability rode entirely
on the MCP subprocess's per-tool blocking sync (the "~15s per write_file"
cost). Now the parent owns the turn-end sync and the bound subprocess defers
its per-tool sync (see test_mcp_sync_gating for the subprocess side).
"""
import os
import time

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient

import api
from src.agents import runtime_registry


class _RecordingProvider:
    def __init__(self):
        self.synced = []

    def workspace_for(self, sid):
        os.makedirs("/tmp/sc-ext-sync-test-ws", exist_ok=True)
        return "/tmp/sc-ext-sync-test-ws"

    def sync(self, sid):
        self.synced.append(sid)


class _FakeRuntime:
    """Minimal extension: emits start/text/done like a real Codex turn."""

    runtime_id = "fake_ext"

    async def run_turn(self, ctx):
        await ctx.emit(runtime_registry.RuntimeEvent.start())
        await ctx.emit(runtime_registry.RuntimeEvent.text("hi"))
        await ctx.emit(runtime_registry.RuntimeEvent.done())


@pytest.fixture()
def ext_ws(monkeypatch):
    api._ACTIVE_TURNS.clear()
    provider = _RecordingProvider()
    monkeypatch.setattr(api, "get_workspace_provider", lambda: provider)
    monkeypatch.setattr(api, "_uid", lambda identity: "u1")
    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {"runtime": "fake_ext"})
    runtime_registry.register_runtime(
        runtime_registry.RuntimeDescriptor(id="fake_ext", display_name="Fake"),
        _FakeRuntime(),
    )
    yield provider
    runtime_registry.unregister_runtime("fake_ext")


def test_extension_turn_syncs_workspace_once_in_background(ext_ws):
    provider = ext_ws
    with TestClient(api.app).websocket_connect("/api/chat/sess-ext") as ws:
        ws.send_json({"message": "hi"})
        while True:
            f = ws.receive_json()
            if f.get("type") in ("done", "error", "stopped"):
                break
        assert f["type"] == "done", f
        # The sync is a fire-and-forget background task on the app loop — the
        # terminal frame must NOT wait on it, so poll briefly for it here.
        deadline = time.time() + 2
        while not provider.synced and time.time() < deadline:
            time.sleep(0.01)
    assert provider.synced == ["sess-ext"], (
        "extension turn must trigger exactly one turn-end workspace sync"
    )
