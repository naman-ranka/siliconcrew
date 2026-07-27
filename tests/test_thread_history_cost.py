"""Regression: GET .../threads/{tid}/history must be a cheap checkpoint read.

Issue #27 — the endpoint took p95 7.6s. Not (as first hypothesised) a
checkpoint-history walk: ``aget_state`` is a single read. The cost was four
avoidable things, all of them synchronous work on the event loop:

1. The session row was queried TWICE per request (``_require_owned`` →
   ``owns_session`` → ``get_session``, then ``_session_model`` →
   ``get_session_metadata`` → the identical ``get_session``).
2. An LLM key was resolved — on hosted an un-pooled Postgres connect plus a
   synchronous Cloud KMS decrypt — for a client that is never invoked.
3. A full ReAct graph was compiled (≈40 tools bound, system prompt re-read from
   disk) and then thrown away after one state read.
4. None of it was offloaded, unlike the sibling endpoints' ``asyncio.to_thread``.

These tests PIN the fixed shape with recording fakes: one session query, one
thread query, ZERO key resolutions, ZERO agent constructions — while the
response payload stays exactly what the agent-graph read produced.
"""
import asyncio
import collections
import json
import os

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.platform_engines.checkpointer import open_sqlite_checkpointer
from src.utils.session_manager import SessionManager

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

import api  # noqa: E402


class _CountingStore:
    """Transparent proxy that tallies which store methods the handler calls."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = collections.Counter()

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            self.calls[name] += 1
            return attr(*args, **kwargs)

        return wrapped


class _RecordingKeyProvider:
    """Stands in for the BYOK provider (vault connect + KMS decrypt on hosted)."""

    def __init__(self):
        self.resolves = []

    def resolve(self, uid, model_name):
        self.resolves.append((uid, model_name))
        from src.platform_engines.llm_keys import LlmKey

        return LlmKey(provider="anthropic", api_key="k", source="env")


class _FakeGraph:
    """What the pre-fix path built and used for exactly one aget_state."""

    def __init__(self, messages):
        self._messages = messages

    async def aget_state(self, config):
        class _Snap:
            values = {"messages": self._messages}

        return _Snap()


# A realistic thread: user turn, tool call, tool result, final answer.
def _messages():
    return [
        SystemMessage(content="you are the architect"),
        HumanMessage(content="lint the counter"),
        AIMessage(content="", tool_calls=[{"name": "linter_tool", "args": {"f": "counter.v"}, "id": "c1"}]),
        ToolMessage(content=json.dumps({"status": "lint_passed"}), tool_call_id="c1"),
        AIMessage(content="Lint is clean."),
    ]


EXPECTED_HISTORY = [
    {"role": "user", "content": "lint the counter"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "name": "linter_tool", "args": {"f": "counter.v"}}],
        "tool_results": [
            {"tool_call_id": "c1", "status": "lint_passed", "content": '{"status": "lint_passed"}'}
        ],
    },
    {"role": "assistant", "content": "Lint is clean.", "tool_calls": []},
]


def _seed_checkpoint(db_path: str, thread_id: str, messages) -> None:
    """Write one committed checkpoint for ``thread_id`` (what a finished turn leaves)."""
    from langgraph.checkpoint.base import empty_checkpoint

    async def _write():
        async with open_sqlite_checkpointer(db_path) as saver:
            ck = empty_checkpoint()
            ck["channel_values"] = {"messages": messages}
            ck["channel_versions"] = {"messages": 1}
            await saver.aput(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                ck,
                {"source": "loop", "step": 1},
                {"messages": 1},
            )

    asyncio.run(_write())


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A real SessionManager + a real sqlite checkpoint, with the expensive
    collaborators replaced by recorders."""
    sm = SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(api, "session_manager", sm)

    db_path = str(tmp_path / "checkpoints.db")
    monkeypatch.setattr(api, "DB_PATH", db_path)

    provider = _RecordingKeyProvider()
    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", provider)

    built = []

    def _make_agent(**kwargs):
        built.append(kwargs)
        return _FakeGraph(_messages())

    monkeypatch.setattr(api, "create_architect_agent", _make_agent)

    sid = sm.create_session("uart_tx")
    tid = sm.list_threads(sid)[0]["id"]
    _seed_checkpoint(db_path, tid, _messages())

    class _Env:
        pass

    e = _Env()
    e.sm, e.sid, e.tid, e.db_path = sm, sid, tid, db_path
    e.provider, e.built = provider, built
    e.client = TestClient(api.app)
    return e


def test_thread_history_costs_one_session_read_and_one_thread_read(env):
    counter = _CountingStore(env.sm._store)
    env.sm._store = counter

    r = env.client.get(f"/api/sessions/{env.sid}/threads/{env.tid}/history")
    assert r.status_code == 200, r.text

    # The duplicate metadata queries: the session row was read twice per request.
    assert counter.calls["get_session"] == 1, counter.calls
    assert counter.calls["get_thread"] == 1, counter.calls


def test_thread_history_never_resolves_a_key_or_builds_an_agent(env):
    r = env.client.get(f"/api/sessions/{env.sid}/threads/{env.tid}/history")
    assert r.status_code == 200, r.text

    # On hosted each resolve is an un-pooled connect + a synchronous KMS
    # decrypt, and each construction compiles a ~40-tool graph and re-reads the
    # system prompt from disk — for a client this endpoint never invokes.
    assert env.provider.resolves == []
    assert env.built == []


def test_thread_history_payload_is_unchanged(env):
    """The cheap read must return exactly what the agent-graph read returned."""
    r = env.client.get(f"/api/sessions/{env.sid}/threads/{env.tid}/history")
    assert r.status_code == 200, r.text
    assert r.json() == EXPECTED_HISTORY


def test_checkpoint_read_matches_langgraph_get_state(tmp_path):
    """The load-bearing equivalence: the messages this endpoint now reads
    straight off the checkpoint are the same objects, in the same order, that
    LangGraph's own ``aget_state`` yields for a committed checkpoint."""
    from langgraph.graph import END, StateGraph
    from langgraph.graph.message import MessagesState

    db_path = str(tmp_path / "eq.db")
    _seed_checkpoint(db_path, "t-eq", _messages())

    async def _compare():
        async with open_sqlite_checkpointer(db_path) as saver:
            config = {"configurable": {"thread_id": "t-eq"}}

            tup = await saver.aget_tuple(config)
            direct = tup.checkpoint["channel_values"]["messages"]

            builder = StateGraph(MessagesState)
            builder.add_node("agent", lambda s: {"messages": []})
            builder.set_entry_point("agent")
            builder.add_edge("agent", END)
            snap = await builder.compile(checkpointer=saver).aget_state(config)
            return direct, snap.values["messages"]

    direct, via_get_state = asyncio.run(_compare())
    assert [(type(m), m.content) for m in direct] == [(type(m), m.content) for m in via_get_state]


def test_history_for_a_thread_without_a_checkpoint_is_empty(env):
    """A brand-new chat has no checkpoint — empty history, not a 500."""
    fresh = env.sm.create_thread(env.sid, title="Chat 2")
    r = env.client.get(f"/api/sessions/{env.sid}/threads/{fresh['id']}/history")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_history_404s_for_a_thread_in_another_session(env):
    other = env.sm.create_session("other")
    r = env.client.get(f"/api/sessions/{other}/threads/{env.tid}/history")
    assert r.status_code == 404
    assert r.json()["detail"] == "Thread not found"


def test_history_404s_for_an_unknown_session(env):
    r = env.client.get(f"/api/sessions/nope/threads/{env.tid}/history")
    assert r.status_code == 404
    assert r.json()["detail"] == "Session not found"


def test_legacy_chat_history_reads_the_default_thread(env):
    """/api/chat/{sid}/history (thread_id == session_id) shares the same reader."""
    _seed_checkpoint(env.db_path, env.sid, _messages())
    r = env.client.get(f"/api/chat/{env.sid}/history")
    assert r.status_code == 200, r.text
    assert r.json() == EXPECTED_HISTORY
    assert env.provider.resolves == []
    assert env.built == []
