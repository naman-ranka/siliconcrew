"""Chat WebSocket auth handshake (naman-ranka/siliconcrew-dev#59).

The bearer token must never ride the URL query string (Cloud Run logs query
strings verbatim → plaintext JWTs in request logs). The connection is
authenticated from a FIRST frame ``{"type": "auth", "token": ...}`` sent right
after open; the legacy ``?token=`` query param stays working for one release as
a deprecated fallback for old clients mid-deploy.

Proven here, end to end through the real endpoint with the same reversible-fake
harness style as tests/test_chat_byok.py:

  * auth frame with a valid token → the turn runs through to ``done``;
  * auth frame with an invalid token → structured error frame, then close 1008;
  * no frame at all within the handshake timeout → close 1008 (timeout is
    monkeypatched tiny — no real sleeps);
  * legacy ``?token=`` with a plain first message still authenticates, and the
    first frame is replayed as the first chat message (nothing is swallowed);
  * auth frame with a null token authenticates as self-host/anonymous does
    (token=None), so signed-out clients keep working.
"""
from contextlib import asynccontextmanager

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api
from src.platform_engines.identity import AuthError, Identity


VALID_TOKEN = "good-jwt"
IDENT = Identity(user_id="u-ws", email="u@x.test", anonymous=False, provider="test")
ANON_IDENT = Identity(user_id="anon-1", email=None, anonymous=True, provider="anon")


# --- a fake agent graph so a turn can run to `done` (mirrors test_chat_byok) --
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
        yield ("updates", {"agent": {"messages": [_FakeMsg()]}})


class _FakeAuthEngine:
    """Records every token authenticate() saw; VALID_TOKEN or None succeed."""

    def __init__(self):
        self.tokens_seen = []

    def authenticate(self, token, session_hint=None):
        self.tokens_seen.append(token)
        if token is None:
            return ANON_IDENT
        if token == VALID_TOKEN:
            return IDENT
        raise AuthError("invalid_token", "Token validation failed.")


@pytest.fixture()
def harness(monkeypatch):
    fake_auth = _FakeAuthEngine()
    monkeypatch.setattr(api, "auth_engine", fake_auth)

    def fake_create_agent(checkpointer=None, model_name=None, api_key=None):
        return _FakeAgent()

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield object()

    class _WS:
        def workspace_for(self, sid):
            return "/tmp/sc-ws-auth-test-ws"

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "create_architect_agent", fake_create_agent)
    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_uid", lambda identity: None)  # self-host scoping

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "gemini-3.1-flash-lite"})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)

    # A key always resolves so the fake agent turn reaches `done`.
    class _AnyKeyProvider:
        def resolve(self, uid, model_name):
            return type("R", (), {"api_key": "k", "source": "byok", "tier": None, "model": None})()

        def note_usage(self, *a, **k):
            pass

    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _AnyKeyProvider())
    return fake_auth


def _drain_to_done(ws):
    frames = []
    while True:
        f = ws.receive_json()
        frames.append(f)
        if f.get("type") in ("done", "error"):
            return frames


def test_auth_frame_with_valid_token_runs_a_turn(harness):
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"type": "auth", "token": VALID_TOKEN})
        ws.send_json({"message": "hi"})
        frames = _drain_to_done(ws)
    assert any(f["type"] == "done" for f in frames)
    # The handshake token is what authenticate() saw — and it never touched the URL.
    assert harness.tokens_seen == [VALID_TOKEN]


def test_auth_frame_with_invalid_token_closes_1008(harness):
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"type": "auth", "token": "forged"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "invalid_token"
        closed = ws.receive()
        assert closed["type"] == "websocket.close"
        assert closed["code"] == 1008


def test_no_auth_frame_times_out_and_closes_1008(harness, monkeypatch):
    monkeypatch.setattr(api, "WS_AUTH_TIMEOUT_SEC", 0.05)
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        closed = ws.receive()  # send nothing; the server must hang up
        assert closed["type"] == "websocket.close"
        assert closed["code"] == 1008
    assert harness.tokens_seen == []


def test_legacy_query_param_still_authenticates(harness):
    """DEPRECATED fallback (#59): an old client that connects with ?token= and
    opens with a plain chat message still works — the first frame is consumed
    as the first message, not dropped."""
    with TestClient(api.app).websocket_connect(f"/api/chat/sess1?token={VALID_TOKEN}") as ws:
        ws.send_json({"message": "hi from an old client"})
        frames = _drain_to_done(ws)
    assert any(f["type"] == "done" for f in frames)
    assert harness.tokens_seen == [VALID_TOKEN]


def test_legacy_query_param_invalid_token_closes_1008(harness):
    with TestClient(api.app).websocket_connect("/api/chat/sess1?token=forged") as ws:
        ws.send_json({"message": "hi"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "invalid_token"
        closed = ws.receive()
        assert closed["type"] == "websocket.close"
        assert closed["code"] == 1008


def test_garbage_text_first_frame_closes_1008(harness):
    """A non-JSON first frame runs BEFORE auth, so any unauthenticated client
    can send one — it must be a controlled 1008 close, never an unhandled
    json.JSONDecodeError escaping as an ASGI traceback."""
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_text("this is not json {")
        closed = ws.receive()
        assert closed["type"] == "websocket.close"
        assert closed["code"] == 1008
    assert harness.tokens_seen == []  # never reached authenticate()


def test_binary_first_frame_closes_1008(harness):
    """A binary first frame makes starlette's receive_json raise
    KeyError('text') — same pre-auth exposure, same controlled close."""
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_bytes(b"\x00\x01\x02")
        closed = ws.receive()
        assert closed["type"] == "websocket.close"
        assert closed["code"] == 1008
    assert harness.tokens_seen == []


def test_auth_frame_null_token_authenticates_like_no_token(harness):
    """Self-host / signed-out clients send {"type":"auth","token":null} — the
    server must authenticate(None) exactly as the old no-query-param path did."""
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"type": "auth", "token": None})
        ws.send_json({"message": "hi"})
        frames = _drain_to_done(ws)
    assert any(f["type"] == "done" for f in frames)
    assert harness.tokens_seen == [None]
