"""E6 frame-sequence regression (plan-mandated): drive the real WS loop with a
fake agent whose astream raises GraphRecursionError and assert the terminal
frames — no raw error frame, an honest continue nudge, a real done — and that
a follow-up turn still works. Harness pattern follows tests/test_chat_byok.py.
"""
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import api
from src.platform_engines.llm_keys import (
    ByokHostedLlmKeyProvider,
    EnvelopeKeyVault,
    InMemoryWrappedKeyStore,
)


class ReversibleCipher:
    """Test double with UNAMBIGUOUS framing (length-prefixed, not delimited).

    The delimiter version was worse here than elsewhere: with no ``assert``, a
    DEK containing ``|`` silently returned a CORRUPTED plaintext (a stray byte
    prepended to the API key) instead of failing loudly. See
    test_byok_endpoints.py.
    """

    def encrypt(self, key, plaintext):
        return len(key).to_bytes(4, "big") + key + plaintext

    def decrypt(self, key, token):
        n = int.from_bytes(token[:4], "big")
        assert token[4:4 + n] == key
        return token[4 + n:]


class FakeKek:
    def wrap_dek(self, dek):
        return b"KEK(" + dek + b")"

    def unwrap_dek(self, wrapped):
        return wrapped[4:-1]


def _vault():
    return EnvelopeKeyVault(InMemoryWrappedKeyStore(), ReversibleCipher(), FakeKek())


class _FakeState:
    values: dict = {}


class _FakeMsg:
    content = "working on it"
    usage_metadata = {"input_tokens": 4, "output_tokens": 6}
    tool_calls: list = []


class _RecursionAgent:
    async def aget_state(self, config):
        return _FakeState()

    async def astream(self, inputs, config, stream_mode=None):
        from langgraph.errors import GraphRecursionError
        yield ("updates", {"agent": {"messages": [_FakeMsg()]}})
        raise GraphRecursionError(
            "Recursion limit of 80 reached without hitting a stop condition."
        )


@pytest.fixture()
def harness(monkeypatch):
    calls = []

    def fake_create_agent(checkpointer=None, model_name=None, api_key=None):
        calls.append({"model_name": model_name, "api_key": api_key})
        return _RecursionAgent()

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield object()

    class _WS:
        def workspace_for(self, sid):
            return "/tmp/sc-e6-test-ws"

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "create_architect_agent", fake_create_agent)
    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_uid", lambda identity: "u1")

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "gemini-3.1-flash-lite"})

    for env in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(env, raising=False)

    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED"))
    return calls


def test_recursion_disposition_frames(harness):
    frames = []
    with TestClient(api.app).websocket_connect("/api/chat/sess-e6") as ws:
        ws.send_json({"message": "build a fifo"})
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f.get("type") in ("done", "error", "stopped"):
                break
    types = [f["type"] for f in frames]
    print("FRAMES:", types)
    assert "error" not in types, f"raw error frame leaked: {frames}"
    nudges = [f for f in frames if f["type"] == "text" and "step budget" in f.get("content", "")]
    assert nudges, f"no honest nudge: {frames}"
    assert types[-1] == "done"
    # follow-up turn works on the same socket
    with TestClient(api.app).websocket_connect("/api/chat/sess-e6") as ws:
        ws.send_json({"message": "continue"})
        f2 = []
        while True:
            f = ws.receive_json()
            f2.append(f)
            if f.get("type") in ("done", "error", "stopped"):
                break
        assert f2[-1]["type"] == "done"
    print("OK")
