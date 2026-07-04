"""Chat WS long-run behavior.

F3: the chat WS sends `ping` keepalives during a silent gap (long tool call)
so an idle proxy/LB timeout doesn't drop the connection mid-run.

P0 #2 (REVIEW_FINDINGS): the heartbeat must NOT cancel the agent stream it
protects — content produced AFTER a gap spanning several heartbeats must still
arrive, followed by a clean `done`.

Stop: a `{"type": "stop"}` frame mid-run cancels the agent and yields an
explicit `stopped` terminal frame.
"""
import asyncio
import os
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient
from langchain_core.messages import AIMessage

import api
from src.platform_engines.llm_keys import LlmKey


class _Msg:
    content = "hello"
    tool_calls: list = []
    usage_metadata = {"input_tokens": 1, "output_tokens": 1}


class _Chunk:
    def __init__(self, text, chunk_id="m1"):
        self.content = text
        self.id = chunk_id


class _State:
    values: dict = {}


class _SlowAgent:
    """Silent gap longer than several (patched) heartbeats, then content."""

    async def aget_state(self, config):
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        await asyncio.sleep(0.35)
        yield ("messages", (_Chunk("hel"), {"langgraph_node": "agent"}))
        yield ("messages", (_Chunk("lo"), {"langgraph_node": "agent"}))
        yield ("updates", {"agent": {"messages": [_Msg()]}})


class _HangingAgent:
    """First text arrives, then the 'tool' hangs until cancelled (stop test)."""

    async def aget_state(self, config):
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        yield ("updates", {"agent": {"messages": [_Msg()]}})
        await asyncio.sleep(30)
        yield ("updates", {"agent": {"messages": [_Msg()]}})


def _patch_common(monkeypatch, make_agent):
    os.makedirs("/tmp/sc-hb-test-ws", exist_ok=True)
    api._ACTIVE_TURNS.clear()
    monkeypatch.setattr(api, "_WS_HEARTBEAT_SEC", 0.1)
    # Disable delta coalescing so every token chunk yields a frame to assert on.
    monkeypatch.setattr(api, "_WS_DELTA_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(api, "create_architect_agent", lambda **k: make_agent())

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
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-5"})


@pytest.fixture()
def slow(monkeypatch):
    _patch_common(monkeypatch, _SlowAgent)


@pytest.fixture()
def hanging(monkeypatch):
    _patch_common(monkeypatch, _HangingAgent)


def _drive(ws):
    frames = []
    while True:
        f = ws.receive_json()
        frames.append(f)
        if f.get("type") in ("done", "error", "stopped"):
            break
    return frames


def test_heartbeat_ping_during_silent_gap_and_content_survives(slow):
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "hi", "turn_id": "turn-abc"})
        frames = _drive(ws)
    types = [f["type"] for f in frames]
    assert "ping" in types, f"expected a heartbeat ping during the silent gap, got {types}"
    # P0 #2: the ping must not have cancelled the run — content still arrives.
    deltas = [f["content"] for f in frames if f["type"] == "text_delta"]
    assert deltas == ["hel", "hello"], f"cumulative token deltas expected, got {deltas}"
    texts = [f["content"] for f in frames if f["type"] == "text"]
    assert texts == ["hello"], f"authoritative text frame must survive the gap, got {types}"
    assert types[-1] == "done"
    # Every frame of the turn echoes the client-provided turn id, so the UI
    # can correlate frames and drop stale ones by id.
    assert all(f.get("turn_id") == "turn-abc" for f in frames), frames


def test_stop_mid_run_yields_stopped_terminal_frame(hanging):
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "hi"})
        # Wait for the first text, then stop while the 'tool' hangs.
        while True:
            f = ws.receive_json()
            if f.get("type") == "text":
                break
        ws.send_json({"type": "stop"})
        while True:
            f = ws.receive_json()
            if f.get("type") in ("done", "error", "stopped"):
                break
    assert f["type"] == "stopped", f"expected explicit stopped frame, got {f}"
    assert "tokens" in f


def test_stop_when_idle_is_ignored(slow):
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"type": "stop"})  # idle no-op, must not error
        ws.send_json({"message": "hi"})
        frames = _drive(ws)
    assert frames[-1]["type"] == "done"


class _CancellableHang:
    """First frame arrives, then hangs; records whether it got cancelled."""

    def __init__(self):
        self.cancelled = False

    async def aget_state(self, config):
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        yield ("updates", {"agent": {"messages": [_Msg()]}})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_new_message_supersedes_headless_run(monkeypatch):
    """The 'sent a message, no reply, but the old run was secretly going' bug:
    a run orphaned by a page refresh must be superseded by the next message on
    the same thread — cancelled, deregistered, and the new turn completes."""
    hang = _CancellableHang()
    agents = iter([hang, _SlowAgent()])
    _patch_common(monkeypatch, lambda: next(agents))

    client = TestClient(api.app)
    with client.websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "start something long"})
        while True:
            if ws.receive_json().get("type") == "text":
                break
        # Leave (page refresh / tab close) while the run hangs → headless run.

    with client.websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "you there"})
        frames = _drive(ws)

    assert frames[-1]["type"] == "done", frames
    assert hang.cancelled is True
    assert api._ACTIVE_TURNS == {}


class _ToolHangAgent:
    """Emits a tool call whose result never comes (hangs); exposes the dangling
    call via aget_state and records aupdate_state repairs."""

    def __init__(self):
        self.updates = []
        self._tool_msg = AIMessage(
            content="", tool_calls=[{"name": "wait_for_synthesis", "args": {}, "id": "tc1"}]
        )

    async def aget_state(self, config):
        st = _State()
        st.values = {"messages": [self._tool_msg]}
        return st

    async def astream(self, inputs, config, stream_mode=None):
        yield ("updates", {"agent": {"messages": [self._tool_msg]}})
        await asyncio.sleep(30)

    async def aupdate_state(self, config, values):
        self.updates.append(values)


def test_stop_writes_interrupted_tool_results_into_checkpoint(monkeypatch):
    """Stop during a tool call closes the turn cleanly: the dangling tool call
    gets an explicit interrupted result written into the checkpoint NOW, not
    lazily on the next turn."""
    agent = _ToolHangAgent()
    _patch_common(monkeypatch, lambda: agent)
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "run it"})
        while True:
            if ws.receive_json().get("type") == "tool_call":
                break
        ws.send_json({"type": "stop"})
        while True:
            f = ws.receive_json()
            if f.get("type") in ("done", "error", "stopped"):
                break
    assert f["type"] == "stopped", f
    repaired = [m for u in agent.updates for m in u.get("messages", [])]
    assert any(getattr(m, "tool_call_id", None) == "tc1" for m in repaired), agent.updates


def test_terminal_frame_survives_bookkeeping_failure(slow, monkeypatch):
    """A stats/sync failure after the run must not swallow `done` — that
    leaves the UI showing Stop forever."""
    def boom(*a, **k):
        raise RuntimeError("stats db down")

    monkeypatch.setattr(api.session_manager, "update_session_stats", boom)
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "hi"})
        frames = _drive(ws)
    assert frames[-1]["type"] == "done"
