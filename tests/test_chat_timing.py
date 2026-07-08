"""Native (LangChain/LangGraph) chat-turn timing instrumentation.

The native WS turn had no first-token / LLM-latency signal, so we couldn't
measure why the native agent takes seconds from send to first token. This
covers the additive, log-only `[CHAT-TIMING]` lines (mirror of the Codex
path's `[CODEX-TIMING]`): they must fall out of the turn without touching the
streaming/backpressure/stop logic.

THE line under test is `event=first_token` — the send->first-streamed-token
number, which must fire exactly once per turn and carry thread + turn so
turn 1 vs 2+ (the implicit-prompt-caching signal) can be correlated.
"""
import io
import os
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient

import api
from src.platform_engines.llm_keys import LlmKey


class _Msg:
    content = "hello"
    tool_calls: list = []
    usage_metadata = {"input_tokens": 7, "output_tokens": 3}


class _Chunk:
    def __init__(self, text, chunk_id="m1"):
        self.content = text
        self.id = chunk_id


class _State:
    values: dict = {}


class _TwoTokenAgent:
    """Yields two streamed model text tokens then the authoritative update —
    enough to prove first_token fires ONCE (not per token)."""

    async def aget_state(self, config):
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        yield ("messages", (_Chunk("hel"), {"langgraph_node": "agent"}))
        yield ("messages", (_Chunk("lo"), {"langgraph_node": "agent"}))
        yield ("updates", {"agent": {"messages": [_Msg()]}})


def _patch_common(monkeypatch, make_agent):
    os.makedirs("/tmp/sc-timing-test-ws", exist_ok=True)
    api._ACTIVE_TURNS.clear()
    monkeypatch.setattr(api, "_WS_HEARTBEAT_SEC", 0.1)
    monkeypatch.setattr(api, "_WS_DELTA_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(api, "create_architect_agent", lambda **k: make_agent())

    @asynccontextmanager
    async def fake_ckpt(_p):
        yield object()

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)

    class _WS:
        def workspace_for(self, sid):
            return "/tmp/sc-timing-test-ws"

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
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-5"})


def _timing_lines(buf: io.StringIO):
    return [l for l in buf.getvalue().splitlines() if l.startswith("[CHAT-TIMING]")]


def test_native_turn_emits_chat_timing(monkeypatch):
    _patch_common(monkeypatch, _TwoTokenAgent)
    buf = io.StringIO()
    monkeypatch.setattr(api.sys, "stderr", buf)

    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "hi", "turn_id": "turn-xyz"})
        while True:
            if ws.receive_json().get("type") in ("done", "error", "stopped"):
                break

    lines = _timing_lines(buf)
    events = [l.split(" event=")[1].split(" ")[0] for l in lines]

    # first_token fires EXACTLY once, even though two tokens streamed.
    assert events.count("first_token") == 1, lines
    # Every native-turn phase is present and correlatable by thread + turn.
    for ev in ("turn_start", "first_model_response", "first_token", "turn_end"):
        assert ev in events, (ev, lines)
    assert all("thread=sess1" in l and "turn=turn-xyz" in l for l in lines), lines

    first = next(l for l in lines if " event=first_token" in l)
    elapsed = float(first.split("elapsed_since_start=")[1].split(" ")[0])
    assert elapsed >= 0.0, first

    end = next(l for l in lines if " event=turn_end" in l)
    assert "input_tokens=7" in end and "output_tokens=3" in end, end


def test_chat_timing_helper_never_raises(monkeypatch):
    """A timing failure must NEVER break or delay a turn — the helper swallows
    everything (e.g. an object whose repr blows up)."""
    class _Boom:
        def __repr__(self):
            raise RuntimeError("boom")

    # Must not raise despite an un-repr-able field.
    api._log_chat_timing("t", "turn", "first_token", elapsed_since_start=_Boom())
