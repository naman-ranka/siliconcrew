"""Golden websocket frames, captured from a REAL graph.

Why this file exists
--------------------
The turn driver in ``api.py`` keys on LangGraph's node names -- ``"agent"`` and
``"tools"`` (see ``_handle_updates``). Every other websocket test in this repo
hand-builds ``{"agent": ...}`` events, so if the framework renames that node,
the fakes keep producing the old shape and the suite stays green while the
product emits no text, no tool cards, no activity rows and no token counts.

These tests drive the SAME websocket handler with a real ``create_react_agent``
graph over a scripted model. Whatever the framework really emits is what the
handler really receives. If a framework upgrade moves the node names, these fail
and the fakes cannot hide it.

They are the safety net for the planned backbone migration. Capture first,
migrate second.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from tests.support.scripted_graph import ai, build_real_graph, echo_tool, exploding_tool

GOLDEN_DIR = Path(__file__).parent / "golden" / "ws_frames"

# Frame fields that legitimately vary run to run. Everything else must match.
_VOLATILE = {"turn_id", "tool_call_id", "id", "segment_id", "duration_ms", "timestamp"}


def _normalise(frames):
    """Strip per-run identifiers so frames compare across runs."""
    out = []
    for f in frames:
        if f.get("type") == "ping":
            continue
        clean = {}
        for k, v in f.items():
            if k in _VOLATILE:
                continue
            if k == "tool" and isinstance(v, dict):
                v = {tk: tv for tk, tv in v.items() if tk not in _VOLATILE}
            clean[k] = v
        out.append(clean)
    return out


def _assert_golden(name, frames):
    """Compare against the stored golden file, writing it on first run."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    actual = _normalise(frames)
    if not path.exists():
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.fail(
            f"golden file {path.name} did not exist and has been written. "
            "Review it by hand, then re-run -- a golden nobody read is not a golden."
        )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"websocket frames changed for scenario {name!r}.\n"
        f"expected: {json.dumps(expected, indent=2, sort_keys=True)}\n"
        f"actual:   {json.dumps(actual, indent=2, sort_keys=True)}"
    )


class _Key:
    api_key = "test-key"
    model = None


class _Provider:
    def resolve(self, uid, model_name):
        return _Key()


@pytest.fixture()
def drive(monkeypatch, tmp_path):
    """Drive the real websocket handler over a real graph."""
    built = {}

    def _install(script, tools=None, recursion_limit=None):
        def fake_create_agent(checkpointer=None, model_name=None, api_key=None):
            graph = build_real_graph(script, tools=tools)
            built["graph"] = graph
            return graph

        monkeypatch.setattr(api, "create_architect_agent", fake_create_agent)
        if recursion_limit is not None:
            settings = api.get_settings()
            monkeypatch.setattr(settings, "chat_recursion_limit", recursion_limit, raising=False)

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield None

    class _WS:
        def workspace_for(self, sid):
            return str(tmp_path)

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _Provider())

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-4-6"})

    def _run(script, message="go", tools=None, recursion_limit=None):
        _install(script, tools=tools, recursion_limit=recursion_limit)
        frames = []
        with TestClient(api.app).websocket_connect("/api/chat/sess-golden") as ws:
            ws.send_json({"message": message})
            while True:
                f = ws.receive_json()
                frames.append(f)
                if f.get("type") in ("done", "error", "stopped"):
                    break
        return frames

    _run.built = built
    return _run


# --- the tripwire ----------------------------------------------------------

def test_graph_node_names_match_what_the_turn_driver_keys_on(drive):
    """THE migration tripwire.

    ``_handle_updates`` dispatches on the literal strings ``"agent"`` and
    ``"tools"``. This asserts the real graph still uses them. When a framework
    upgrade renames a node this fails loudly, instead of the product silently
    going quiet.
    """
    import asyncio

    graph = build_real_graph([
        ai("", tool_calls=[{"id": "c1", "name": "echo_tool", "args": {"text": "hi"}}]),
        ai("finished"),
    ])

    async def collect():
        keys = []
        async for mode, payload in graph.astream(
            {"messages": [("user", "go")]},
            {"configurable": {"thread_id": "t-nodes"}, "recursion_limit": 10},
            stream_mode=["updates", "messages"],
        ):
            if mode == "updates":
                keys.extend(payload.keys())
        return keys

    keys = asyncio.run(collect())
    assert set(keys) == {"agent", "tools"}, (
        f"graph emitted update keys {sorted(set(keys))}. api.py's _handle_updates "
        "dispatches on 'agent' and 'tools' -- if these no longer match, the turn "
        "driver produces NO frames and the product is silently dead. Update both "
        "together."
    )


# --- golden scenarios ------------------------------------------------------

def test_g1_text_only_turn(drive):
    frames = drive([ai("hello from the agent", usage={"input_tokens": 4, "output_tokens": 6})])
    _assert_golden("g1_text_only", frames)


def test_g2_multi_tool_turn(drive):
    frames = drive([
        ai("", tool_calls=[{"id": "c1", "name": "echo_tool", "args": {"text": "one"}}]),
        ai("", tool_calls=[{"id": "c2", "name": "echo_tool", "args": {"text": "two"}}]),
        ai("both done", usage={"input_tokens": 10, "output_tokens": 3}),
    ])
    _assert_golden("g2_multi_tool", frames)


def test_g3_a_raising_tool_kills_the_whole_turn(drive):
    """Documents CURRENT behaviour, which is not obviously the behaviour we want.

    A tool that RAISES propagates straight out of ``astream``: the turn ends on
    an ``error`` frame and the agent never gets the failure back as a tool
    result, so it cannot adapt or explain. The script here queues a follow-up
    reply and that reply never happens.

    Latent rather than daily: SiliconCrew's real tools return error dicts
    instead of raising (``run_linter`` and ``run_simulation`` contain no ``raise``
    at all), so this path is reached only by a genuine crash inside a tool -- an
    unhandled OSError, a bad import, a docker hiccup. When that happens the user
    loses the turn instead of getting a diagnosis.

    Captured as a golden so the behaviour is visible and any change to it is
    deliberate. Whether tool exceptions should come back as tool results belongs
    to the tool-metadata phase, not here.
    """
    frames = drive([
        ai("", tool_calls=[{"id": "c1", "name": "exploding_tool", "args": {"text": "kaboom"}}]),
        ai("this reply never arrives"),
    ])
    assert [f["type"] for f in frames][-1] == "error"
    assert not any(f["type"] == "text" for f in frames), (
        "the agent produced text after a raising tool -- behaviour changed, "
        "update this test and its golden deliberately"
    )
    _assert_golden("g3_tool_error", frames)


def test_g7_token_accounting_survives(drive):
    """Tokens are read from the 'agent' node only, and feed session stats and
    the hosted spend limiter. A node rename zeroes both silently."""
    frames = drive([
        ai("", tool_calls=[{"id": "c1", "name": "echo_tool", "args": {"text": "x"}}],
           usage={"input_tokens": 7, "output_tokens": 2}),
        ai("done", usage={"input_tokens": 5, "output_tokens": 4}),
    ])
    done = [f for f in frames if f["type"] == "done"]
    assert done, "no terminal done frame"
    tokens = done[-1]["tokens"]
    assert tokens["input"] == 12, f"input tokens not summed across steps: {tokens}"
    assert tokens["output"] == 6, f"output tokens not summed across steps: {tokens}"


def test_frames_carry_a_turn_id(drive):
    """Every frame is stamped so the UI can drop stale frames by id."""
    frames = drive([ai("hi")])
    assert frames, "no frames at all"
    assert all("turn_id" in f for f in frames), (
        "a frame without turn_id cannot be attributed to a turn: "
        f"{[f['type'] for f in frames if 'turn_id' not in f]}"
    )
