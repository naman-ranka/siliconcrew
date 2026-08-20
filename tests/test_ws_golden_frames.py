"""Golden websocket frames, captured from a REAL graph.

Why this file exists
--------------------
The turn driver in ``api.py`` keys on LangGraph's node names -- ``MODEL_NODE``
and ``TOOLS_NODE`` (see ``_handle_updates``). Every other websocket test in this
repo hand-builds ``{MODEL_NODE: ...}`` events, so if the framework renames that node,
the fakes keep producing the old shape and the suite stays green while the
product emits no text, no tool cards, no activity rows and no token counts.

These tests drive the SAME websocket handler with a real ``create_agent``
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
from src.agents.architect import MODEL_NODE, TOOLS_NODE, architect_middleware
from tests.support.scripted_graph import (
    ai,
    build_real_graph,
    build_real_graph_with_model,
    echo_tool,
    exploding_tool,
)

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

    ``_handle_updates`` dispatches on ``MODEL_NODE`` / ``TOOLS_NODE``, declared
    in ``src.agents.architect`` beside the factory that builds the graph. This
    asserts the graph the framework actually compiles still emits exactly those
    names -- in the ``updates`` stream AND in ``metadata["langgraph_node"]`` on
    streamed tokens. The framework has renamed the model node once already
    (``agent`` under ``create_react_agent``, ``model`` under ``create_agent``);
    when it happens again this fails loudly instead of the product silently
    going quiet.
    """
    import asyncio

    graph = build_real_graph([
        ai("", tool_calls=[{"id": "c1", "name": "echo_tool", "args": {"text": "hi"}}]),
        ai("finished"),
    ])

    async def collect():
        keys, token_nodes = [], set()
        async for mode, payload in graph.astream(
            {"messages": [("user", "go")]},
            {"configurable": {"thread_id": "t-nodes"}, "recursion_limit": 10},
            stream_mode=["updates", "messages"],
        ):
            if mode == "updates":
                keys.extend(payload.keys())
            else:
                _chunk, meta = payload
                token_nodes.add((meta or {}).get("langgraph_node"))
        return keys, token_nodes

    keys, token_nodes = asyncio.run(collect())
    assert set(keys) == {MODEL_NODE, TOOLS_NODE}, (
        f"graph emitted update keys {sorted(set(keys))}. api.py's _handle_updates "
        f"dispatches on {MODEL_NODE!r} and {TOOLS_NODE!r} -- if these no longer "
        "match, the turn driver produces NO frames and the product is silently "
        "dead. Update src.agents.architect's constants and this test together."
    )
    assert MODEL_NODE in token_nodes, (
        f"streamed token metadata carried langgraph_node {sorted(token_nodes)}, "
        f"not {MODEL_NODE!r}. api.py gates every text_delta frame on that value, "
        "so a mismatch means the chat never streams."
    )


def test_no_middleware_adds_a_graph_node():
    """Node-style middleware are not free: each one consumes a graph step per
    model call, so each one silently shrinks how much work a turn can do at a
    fixed recursion limit. The shipped list must stay wrap-style only -- if that
    ever changes, CHAT_RECURSION_LIMIT has to be re-derived in the same commit.
    """
    graph = build_real_graph([ai("hi")])
    nodes = set(graph.get_graph().nodes)
    assert nodes == {"__start__", MODEL_NODE, TOOLS_NODE, "__end__"}, (
        f"the compiled graph has nodes {sorted(nodes)}. A middleware added a "
        "node, which costs a graph step per model call -- re-derive "
        "CHAT_RECURSION_LIMIT (settings.py) and update this test deliberately."
    )


def test_no_shipped_middleware_owns_its_own_model():
    """A middleware that constructs its own LLM (``SummarizationMiddleware(model=)``,
    ``ModelFallbackMiddleware``) bypasses the request-scoped key resolution in
    api.py, the hosted model pin, cost accounting and the hosted-tier spend
    limiter. That is an uncapped BYOK/free-tier hole, so the shipped list must
    hold no model objects at all."""
    from langchain_core.language_models import BaseLanguageModel

    for mw in architect_middleware():
        for attr, value in vars(mw).items():
            assert not isinstance(value, BaseLanguageModel), (
                f"{type(mw).__name__}.{attr} holds its own model. Every model in "
                "the agent must come from the same create_llm(model_name, "
                "api_key=...) call so BYOK keys, the hosted model pin, cost "
                "accounting and the spend limiter all apply."
            )


def test_the_step_budget_a_turn_actually_gets_is_unchanged():
    """The recursion-limit arithmetic, pinned.

    ``create_react_agent`` with a ``pre_model_hook`` ran THREE nodes per round
    (hook, agent, tools); ``create_agent`` with wrap-style middleware runs TWO
    (model, tools). At an unchanged limit the agent would silently get ~48%
    more model calls per turn -- longer turns, more spend, a later step-budget
    nudge. The default was re-derived from 80 to 54 to hold the real budget at
    the 27 model calls it has been. This asserts the number the user feels.
    """
    import asyncio
    import os

    from langgraph.errors import GraphRecursionError

    from src.platform_engines.settings import get_settings

    if os.environ.get("CHAT_RECURSION_LIMIT"):
        pytest.skip("CHAT_RECURSION_LIMIT is overridden in this environment; "
                    "this test pins the SHIPPED default")
    limit = get_settings().chat_recursion_limit
    graph, model = build_real_graph_with_model(
        [ai("", tool_calls=[{"id": "c1", "name": "echo_tool", "args": {"text": "x"}}])]
    )

    async def run():
        try:
            async for _ in graph.astream(
                {"messages": [("user", "go")]},
                {"configurable": {"thread_id": "t-budget"}, "recursion_limit": limit},
                stream_mode=["updates"],
            ):
                pass
        except GraphRecursionError:
            pass

    asyncio.run(run())
    # `bind_tools` returns self, so the scripted model counts its own
    # round-trips in `.calls` no matter how the graph binds it.
    calls = len(model.calls)
    assert calls == 27, (
        f"a turn at CHAT_RECURSION_LIMIT={limit} gets {calls} model calls, not "
        "27. The step budget users actually feel changed -- if that is intended, "
        "it is a product decision, not a side effect."
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
