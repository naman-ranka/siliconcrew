"""F3: the chat WS sends a `ping` keepalive during a silent gap (long tool call),
so an idle proxy/LB timeout doesn't drop the connection mid-run."""
import asyncio
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient

import api
from src.platform_engines.llm_keys import LlmKey


class _Msg:
    content = "hello"
    tool_calls: list = []
    usage_metadata = {"input_tokens": 1, "output_tokens": 1}


class _State:
    values: dict = {}


class _SlowAgent:
    async def aget_state(self, config):
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        # Silent gap longer than the (patched) heartbeat → forces ping(s).
        await asyncio.sleep(0.35)
        yield {"agent": {"messages": [_Msg()]}}


@pytest.fixture()
def slow(monkeypatch):
    monkeypatch.setattr(api, "_WS_HEARTBEAT_SEC", 0.1)
    monkeypatch.setattr(api, "create_architect_agent", lambda **k: _SlowAgent())

    @asynccontextmanager
    async def fake_ckpt(_p):
        yield object()

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)

    class _WS:
        def workspace_for(self, sid):
            return "/tmp/sc-hb-test-ws"

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_uid", lambda identity: "u1")

    class _Prov:
        def resolve(self, uid, model_name):
            return LlmKey(provider="anthropic", api_key="k", source="env")

    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _Prov())

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "ensure_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-4-6"})


def test_heartbeat_ping_during_silent_gap(slow):
    frames = []
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "hi"})
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f.get("type") in ("done", "error"):
                break
    types = [f["type"] for f in frames]
    assert "ping" in types, f"expected a heartbeat ping during the silent gap, got {types}"
    assert "done" in types
