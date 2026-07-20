"""4B (hosted-latency plan): an extension (Codex) turn persists the workspace
ONCE per turn, in the background — the native path's proven cadence.

Before the fix the extension branch in the chat WS handler ``continue``d past
the native path's turn-end background sync, so Codex durability rode entirely
on the MCP subprocess's per-tool blocking sync (the "~15s per write_file"
cost). Now the parent owns the turn-end sync and the bound subprocess defers
its per-tool sync (see test_mcp_sync_gating for the subprocess side).
"""
import asyncio
import os
import time

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient

import api
from src.agents import runtime_registry
from src.platform_engines.workspace_flusher import WorkspaceFlusher


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


class _ToolFrameThenHangRuntime:
    """Emits a tool boundary then hangs — models the mid-turn window where a
    deploy drain used to lose every file the agent had written so far."""

    runtime_id = "fake_ext"

    async def run_turn(self, ctx):
        await ctx.emit(runtime_registry.RuntimeEvent.start())
        await ctx.emit(runtime_registry.RuntimeEvent.tool_call(
            {"id": "t1", "name": "write_file", "args": {}}
        ))
        await ctx.emit(runtime_registry.RuntimeEvent.tool_result(
            "t1", status="success", content="ok"
        ))
        await asyncio.sleep(30)  # cancelled by the stop frame
        await ctx.emit(runtime_registry.RuntimeEvent.done())


@pytest.fixture()
def ext_ws(monkeypatch):
    api._ACTIVE_TURNS.clear()
    provider = _RecordingProvider()
    monkeypatch.setattr(api, "get_workspace_provider", lambda: provider)
    # The turn-end flush goes through the write-behind flusher now (session-
    # durability plan); point a fresh flusher at the fake provider and reset
    # the singleton afterwards so no other test inherits it.
    flusher = WorkspaceFlusher(provider_resolver=lambda: provider,
                               base_cooldown_sec=0.01)
    monkeypatch.setattr(api, "get_workspace_flusher", lambda: flusher)
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
    flusher.close()
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


def test_tool_frames_flush_mid_turn_before_the_turn_ends(ext_ws):
    """Regression (fails pre-fix): a tool boundary during a still-running turn
    must already have flushed the workspace — durability may not wait for the
    turn to finish (that was the whole-turn data-loss window on deploys)."""
    provider = ext_ws
    runtime_registry.unregister_runtime("fake_ext")
    runtime_registry.register_runtime(
        runtime_registry.RuntimeDescriptor(id="fake_ext", display_name="Fake"),
        _ToolFrameThenHangRuntime(),
    )
    with TestClient(api.app).websocket_connect("/api/chat/sess-ext") as ws:
        ws.send_json({"message": "hi"})
        while True:
            f = ws.receive_json()
            if f.get("type") == "tool_result":
                break
        # The turn is still hanging; the flush must land regardless.
        deadline = time.time() + 2
        while not provider.synced and time.time() < deadline:
            time.sleep(0.01)
        assert provider.synced and set(provider.synced) == {"sess-ext"}, (
            "tool-boundary frames must trigger a mid-turn workspace flush"
        )
        ws.send_json({"type": "stop"})
        while True:
            f = ws.receive_json()
            if f.get("type") in ("stopped", "done", "error"):
                break
