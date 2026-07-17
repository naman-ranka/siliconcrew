"""Slice 1 — the chat WebSocket resolves an LLM key and passes it to the agent.

Proves the BYOK wiring end to end at the api layer with the in-memory vault +
reversible fakes (same style as test_llm_keys): a user with a stored key gets it;
a Gemini user with no key gets the capped hosted key; a non-Gemini user with no
key gets a structured ``no_key`` error frame (not a 500); an exhausted hosted
tier gets a ``hosted_tier_exhausted`` frame; reading history works with no key.
"""
from contextlib import asynccontextmanager

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api
from src.platform_engines.llm_keys import (
    ByokHostedLlmKeyProvider,
    EnvelopeKeyVault,
    HostedTierLimiter,
    HostedTierLimits,
    InMemoryWrappedKeyStore,
)


# --- reversible envelope fakes (mirror test_llm_keys) -----------------------
class ReversibleCipher:
    def encrypt(self, key: bytes, plaintext: bytes) -> bytes:
        return key + b"||" + plaintext

    def decrypt(self, key: bytes, token: bytes) -> bytes:
        k, _, pt = token.partition(b"||")
        assert k == key
        return pt


class FakeKek:
    def wrap_dek(self, dek: bytes) -> bytes:
        return b"KEK(" + dek + b")"

    def unwrap_dek(self, wrapped: bytes) -> bytes:
        return wrapped[4:-1]


def _vault():
    return EnvelopeKeyVault(InMemoryWrappedKeyStore(), ReversibleCipher(), FakeKek())


# --- a fake agent graph that records how it was constructed -----------------
class _FakeState:
    values: dict = {}


class _FakeMsg:
    content = "hello from the agent"
    usage_metadata = {"input_tokens": 4, "output_tokens": 6}
    tool_calls: list = []


class _FakeAgent:
    async def aget_state(self, config):
        return _FakeState()

    async def astream(self, inputs, config, stream_mode=None):
        # The WS streams with stream_mode=["updates", "messages"], so events
        # arrive as (mode, payload) tuples.
        yield ("updates", {"agent": {"messages": [_FakeMsg()]}})


@pytest.fixture()
def harness(monkeypatch):
    """Patch the WS's collaborators so we can drive it in-process and capture the
    (model_name, api_key) the agent was built with."""
    calls = []

    def fake_create_agent(checkpointer=None, model_name=None, api_key=None):
        calls.append({"model_name": model_name, "api_key": api_key})
        return _FakeAgent()

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield object()

    class _WS:
        def workspace_for(self, sid):
            return "/tmp/sc-byok-test-ws"

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "create_architect_agent", fake_create_agent)
    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())

    # Simulate a hosted, signed-in identity with a real tenant id so BYOK (which
    # is keyed by user_id) is exercised. (Self-host uid is None → BYOK skipped.)
    monkeypatch.setattr(api, "_uid", lambda identity: "u1")

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)

    # No ambient env keys — so "no key" really means no key.
    for env in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(env, raising=False)

    def set_model(model_name):
        monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": model_name})

    def set_provider(provider):
        monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", provider)

    def drive(message="hi"):
        frames = []
        with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
            ws.send_json({"message": message})
            while True:
                f = ws.receive_json()
                frames.append(f)
                if f.get("type") in ("done", "error"):
                    break
        return frames

    return type("H", (), {"calls": calls, "set_model": set_model, "set_provider": set_provider, "drive": staticmethod(drive)})


def test_byok_key_is_passed_to_the_agent(harness):
    vault = _vault()
    vault.store_key("u1", "anthropic", "sk-ant-user-123")  # the harness's hosted uid
    harness.set_provider(ByokHostedLlmKeyProvider(vault))
    harness.set_model("claude-sonnet-4-6")

    frames = harness.drive()

    assert any(f["type"] == "done" for f in frames)
    assert harness.calls, "agent was never constructed"
    assert harness.calls[-1]["api_key"] == "sk-ant-user-123"
    assert harness.calls[-1]["model_name"] == "claude-sonnet-4-6"


def test_gemini_with_no_key_uses_capped_hosted_key(harness, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    harness.set_provider(
        ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="hosted-gemini-secret", hosted_model="gemini-3.1-flash-lite")
    )
    harness.set_model("gemini-3.1-flash-lite")

    frames = harness.drive()

    assert any(f["type"] == "done" for f in frames)
    assert harness.calls[-1]["api_key"] == "hosted-gemini-secret"


def test_non_gemini_no_key_emits_structured_no_key_error(harness):
    harness.set_provider(ByokHostedLlmKeyProvider(_vault()))  # no hosted gemini key
    harness.set_model("claude-sonnet-4-6")

    frames = harness.drive()

    err = [f for f in frames if f["type"] == "error"]
    assert err and err[-1]["code"] == "no_key"
    assert not harness.calls, "agent must not be built when no key resolves"


def test_hosted_tier_exhausted_emits_structured_error(harness, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    limiter = HostedTierLimiter(HostedTierLimits(global_cost_ceiling_usd=0.0))
    harness.set_provider(
        ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="hosted-gemini-secret", limiter=limiter)
    )
    harness.set_model("gemini-3.1-flash-lite")

    frames = harness.drive()

    err = [f for f in frames if f["type"] == "error"]
    assert err and err[-1]["code"] == "hosted_tier_exhausted"


@pytest.mark.anyio
async def test_history_read_tolerates_no_key(monkeypatch):
    """Reading history never 500s when no key is configured — resolve best-effort,
    pass api_key=None, return empty history."""
    class _NoKeyProvider:
        def resolve(self, uid, model_name):
            raise ValueError("No key available")

    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _NoKeyProvider())
    monkeypatch.setattr(api, "create_architect_agent", lambda **k: _FakeAgent())

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield object()

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)

    hist = await api._read_thread_history("t1", "claude-sonnet-4-6", uid=None)
    assert hist == []


@pytest.fixture
def anyio_backend():
    return "asyncio"
