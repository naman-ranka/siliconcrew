"""Context compaction: what the MODEL sees shrinks, what is STORED never does.

Why this file leads with a non-destruction test
-----------------------------------------------
There is no ``messages`` table. The transcript a user reads in the chat panel is
rebuilt out of the LangGraph checkpoint by ``api._read_thread_history`` — the
checkpoint IS the user's history, and there is no backup to restore it from. So
a compaction strategy that rewrites stored messages does not "save context", it
deletes a design session. ``SummarizationMiddleware`` does exactly that (it is a
``before_model`` hook and its state update replaces the message list, the user's
own turns included), which is why the shipped strategy is
``ContextEditingMiddleware``: a ``wrap_model_call`` hook that deep-copies the
message list, edits the copy, and hands the copy to the model. The checkpoint
never sees it.

The first test here compares the RENDERED transcript with compaction forced on
against the same thread with it off, through the real render path. If a future
change swaps in a middleware that writes state, that test fails before anyone
ships it.

The second property is the one that breaks a session mid-flight rather than
after it: a model request that carries a tool call whose result is missing is a
provider 400. ``ClearToolUsesEdit`` never removes a message — it replaces a
``ToolMessage``'s CONTENT with a placeholder — so the call/result pairing is
preserved structurally rather than by careful bookkeeping. These tests assert
that, including at the boundary where the "keep the most recent N" cut falls
exactly between an AI tool call and its result.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

import api
from src.agents.architect import architect_middleware
from src.platform_engines.settings import get_settings, reset_settings_cache
from tests.support.scripted_graph import ai, build_real_graph_with_model


@tool
def note_tool(text: str) -> str:
    """Return a chunky note. Test double, not a real SiliconCrew tool."""
    return f"NOTE-{text}: " + ("detail " * 40)


USER_SENTENCE = "PLEASE-REMEMBER-THIS-EXACT-USER-SENTENCE"


def _script(n_tools: int):
    """``n_tools`` tool round-trips, then a final text answer."""
    return [
        ai("", tool_calls=[{"id": f"c{i}", "name": "note_tool", "args": {"text": f"t{i}"}}])
        for i in range(1, n_tools + 1)
    ] + [ai("all done", usage={"input_tokens": 11, "output_tokens": 7})]


@pytest.fixture()
def compaction(monkeypatch):
    """Set the compaction knobs and rebuild the settings cache around a test."""

    def _set(trigger, keep=3):
        monkeypatch.setenv("CHAT_CONTEXT_EDIT_TRIGGER", str(trigger))
        monkeypatch.setenv("CHAT_CONTEXT_EDIT_KEEP", str(keep))
        reset_settings_cache()

    yield _set
    monkeypatch.delenv("CHAT_CONTEXT_EDIT_TRIGGER", raising=False)
    monkeypatch.delenv("CHAT_CONTEXT_EDIT_KEEP", raising=False)
    reset_settings_cache()


def _run_turn(thread_id, n_tools=5, message=USER_SENTENCE):
    """One real turn on a real graph carrying the SHIPPED middleware list.

    Returns ``(graph, stored_messages, model_views)`` where ``model_views`` is
    what the scripted model was actually handed on each round — the only honest
    way to tell "compaction fired" from "compaction was configured".
    """
    saver = InMemorySaver()
    graph, model = build_real_graph_with_model(
        _script(n_tools), tools=[note_tool], checkpointer=saver
    )
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    async def go():
        async for _ in graph.astream(
            {"messages": [("user", message)]}, config, stream_mode=["updates"]
        ):
            pass
        return await graph.aget_state(config)

    state = asyncio.run(go())
    return graph, list(state.values["messages"]), [list(v) for v in model.seen]


def _render(graph, thread_id, monkeypatch):
    """The real transcript render path, over the graph's real checkpoint."""

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield None

    class _Key:
        api_key = "test-key"
        model = None

    class _Provider:
        def resolve(self, uid, model_name):
            return _Key()

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _Provider())
    monkeypatch.setattr(api, "_CODEX_STORE", None)
    monkeypatch.setattr(
        api, "create_architect_agent", lambda **kw: graph
    )
    return asyncio.run(api._read_thread_history(thread_id, "claude-sonnet-4-6"))


def _saw_placeholder(views):
    return any("[cleared]" in str(m.content) for view in views for m in view)


def _stored_shape(messages):
    """Everything about a stored message the transcript render reads."""
    return [
        (
            m.type,
            m.content,
            tuple(
                (tc.get("id"), tc.get("name"), repr(tc.get("args")))
                for tc in (getattr(m, "tool_calls", None) or [])
            ),
            getattr(m, "tool_call_id", None),
        )
        for m in messages
    ]


# --- THE test: stored history survives compaction --------------------------

def test_the_rendered_transcript_is_identical_with_and_without_compaction(
    compaction, monkeypatch
):
    """Compaction changes what the model sees, never what the user reads back.

    Two identical turns, one with compaction forced to fire on every model call
    and one with it off, rendered through ``api._read_thread_history``. The two
    transcripts must match exactly — text, tool calls, tool results and order.
    """
    compaction(0)
    off_graph, off_stored, off_views = _run_turn("t-compaction-off")

    compaction(1, keep=1)
    on_graph, on_stored, on_views = _run_turn("t-compaction-on")

    # The test proves nothing unless compaction demonstrably ran.
    assert _saw_placeholder(on_views), (
        "compaction never fired, so this test asserted nothing. The trigger is "
        "in tokens; check CHAT_CONTEXT_EDIT_TRIGGER wiring."
    )
    assert not _saw_placeholder(off_views)

    assert _stored_shape(on_stored) == _stored_shape(off_stored), (
        "the stored messages differ between a compacted and an uncompacted "
        "thread. Compaction is writing to the checkpoint — that IS the user's "
        "chat history and there is no messages table to restore it from."
    )
    assert any(USER_SENTENCE in str(m.content) for m in on_stored), (
        "the user's own message is gone from the checkpoint"
    )
    assert not any("[cleared]" in str(m.content) for m in on_stored), (
        "a placeholder reached the checkpoint"
    )

    off_history = _render(off_graph, "t-compaction-off", monkeypatch)
    on_history = _render(on_graph, "t-compaction-on", monkeypatch)
    assert on_history == off_history
    assert off_history, "the control rendered nothing, so equality is vacuous"
    # And the real tool output is what the user reads, not the placeholder.
    assert any(
        "NOTE-t1" in str(r)
        for turn in on_history
        for r in turn.get("tool_results", [])
    ), "the user's transcript lost the real tool output"


# --- pairing ---------------------------------------------------------------

def _assert_pairs_intact(view):
    """Every tool call in a model view has its result, and vice versa.

    A model view is the history as it stands when the model is asked to speak,
    and the tools node has always run before control returns to the model — so
    an unanswered call in this list is not "in flight", it is the shape the
    provider rejects with a 400.
    """
    called, answered = set(), set()
    for m in view:
        if isinstance(m, AIMessage):
            called.update(tc.get("id") for tc in (m.tool_calls or []))
        elif isinstance(m, ToolMessage):
            answered.add(m.tool_call_id)
    assert called == answered, (
        f"the model view has tool calls with no result "
        f"({sorted(called - answered)}) or results with no call "
        f"({sorted(answered - called)}) — that is a provider 400 mid-session"
    )


def test_a_tool_call_is_never_separated_from_its_result(compaction):
    """Compaction rewrites content, it never removes a message.

    ``keep=1`` puts the retention boundary between an AI tool call and its own
    result on every round after the first, which is exactly where a
    trim-by-index strategy would sever the pair.
    """
    compaction(1, keep=1)
    _graph, _stored, views = _run_turn("t-pairing", n_tools=6)

    assert _saw_placeholder(views)
    for view in views:
        _assert_pairs_intact(view)

    compaction(0)
    _g2, _s2, off_views = _run_turn("t-pairing-off", n_tools=6)
    # Same number of messages on every round: nothing was dropped, only edited.
    assert [len(v) for v in views] == [len(v) for v in off_views], (
        "compaction changed the message COUNT the model sees. The shipped "
        "strategy must only rewrite content — dropping messages is how a "
        "tool call loses its result."
    )
    assert [[m.type for m in v] for v in views] == [
        [m.type for m in v] for v in off_views
    ]


def test_every_cleared_result_still_carries_its_tool_call_id(compaction):
    """The placeholder is a ToolMessage, not a hole: id and position survive."""
    compaction(1, keep=1)
    _graph, _stored, views = _run_turn("t-ids", n_tools=5)

    last = views[-1]
    cleared = [m for m in last if isinstance(m, ToolMessage) and m.content == "[cleared]"]
    assert cleared, "nothing was cleared in the final view"
    for m in cleared:
        assert m.tool_call_id, "a cleared result lost its tool_call_id"
        owner = [
            a
            for a in last
            if isinstance(a, AIMessage)
            and any(tc.get("id") == m.tool_call_id for tc in (a.tool_calls or []))
        ]
        assert owner, f"cleared result {m.tool_call_id} has no originating call"


# --- resume + the start-of-turn dangling repair ----------------------------

def test_a_compacted_thread_resumes_and_the_dangling_repair_still_works(compaction):
    """An interrupted run leaves a tool call with no result in the checkpoint.

    ``api._pending_tool_call_ids`` reads that from the CHECKPOINT, and the next
    turn injects an interrupted-result ToolMessage for each one. Compaction must
    not disturb either half: it never touches the checkpoint the repair reads,
    and the repair's own ToolMessage is stored verbatim even when the model view
    later shows it cleared.
    """
    compaction(1, keep=1)
    saver = InMemorySaver()
    graph, model = build_real_graph_with_model(
        [ai("recovered", usage={"input_tokens": 3, "output_tokens": 2})],
        tools=[note_tool],
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "t-resume"}, "recursion_limit": 20}

    interrupted = AIMessage(
        content="",
        tool_calls=[
            {"id": "dangling-1", "name": "note_tool", "args": {"text": "x"}, "type": "tool_call"}
        ],
    )

    async def go():
        await graph.aupdate_state(
            config, {"messages": [("user", USER_SENTENCE), interrupted]}
        )
        snapshot = await graph.aget_state(config)
        pending = api._pending_tool_call_ids(snapshot.values["messages"])

        repairs = [
            ToolMessage(
                content="[Tool execution was interrupted. Please retry the operation.]",
                tool_call_id=tid,
            )
            for tid in pending
        ]
        async for _ in graph.astream(
            {"messages": [*repairs, ("user", "carry on")]}, config, stream_mode=["updates"]
        ):
            pass
        return pending, await graph.aget_state(config)

    pending, state = asyncio.run(go())
    assert pending == ["dangling-1"], (
        "the dangling-call repair no longer sees the interrupted call. It reads "
        "the checkpoint, which compaction must never edit."
    )

    stored = list(state.values["messages"])
    repair_stored = [
        m for m in stored if isinstance(m, ToolMessage) and m.tool_call_id == "dangling-1"
    ]
    assert len(repair_stored) == 1
    assert "interrupted" in repair_stored[0].content, (
        "the repair's own result was rewritten in the checkpoint"
    )
    assert any(USER_SENTENCE in str(m.content) for m in stored)
    for view in model.seen:
        _assert_pairs_intact(view)


# --- the shipped configuration --------------------------------------------

def test_the_architect_ships_compaction_and_it_costs_no_graph_step():
    """Wrap-style, so the per-turn step budget arithmetic is untouched.

    A node-style middleware would add a graph node and silently shrink how much
    work a turn can do at a fixed ``CHAT_RECURSION_LIMIT``. The node-count and
    model-call assertions live in ``tests/test_ws_golden_frames.py``; this one
    pins that the shipped middleware only implements the wrap hooks.
    """
    from langchain.agents.middleware import AgentMiddleware, ContextEditingMiddleware

    shipped = [mw for mw in architect_middleware() if isinstance(mw, ContextEditingMiddleware)]
    assert len(shipped) == 1, "the architect must ship exactly one context editor"
    mw = shipped[0]
    for hook in ("before_model", "after_model", "before_agent", "after_agent"):
        assert getattr(type(mw), hook, None) is getattr(AgentMiddleware, hook, None), (
            f"{type(mw).__name__} implements the node-style hook {hook!r}; that "
            "costs a graph step per model call — re-derive CHAT_RECURSION_LIMIT."
        )


def test_compaction_is_configured_from_settings_and_can_be_turned_off(compaction):
    """One knob, in tokens; zero means off. No second source of truth."""
    from langchain.agents.middleware import ContextEditingMiddleware

    compaction(4321, keep=7)
    edits = [
        e
        for mw in architect_middleware()
        if isinstance(mw, ContextEditingMiddleware)
        for e in mw.edits
    ]
    assert [(e.trigger, e.keep) for e in edits] == [(4321, 7)]

    compaction(0)
    assert not [
        mw for mw in architect_middleware() if isinstance(mw, ContextEditingMiddleware)
    ]


def test_the_context_editor_counts_tokens_without_calling_a_model():
    """``token_count_method='model'`` would put a provider round-trip in front of
    every model call (and for Anthropic, a real count-tokens API request). The
    shipped setting is the local approximation."""
    from langchain.agents.middleware import ContextEditingMiddleware

    for mw in architect_middleware():
        if isinstance(mw, ContextEditingMiddleware):
            assert mw.token_count_method == "approximate"


def test_the_shipped_trigger_leaves_room_under_the_smallest_context_window():
    """The trigger counts MESSAGE tokens only — no system prompt, no tool
    schemas, no room for the reply. It must sit well under the smallest window
    any catalog model has (200k, Anthropic), or compaction fires after the
    provider has already refused the request."""
    import os

    if os.environ.get("CHAT_CONTEXT_EDIT_TRIGGER"):
        pytest.skip("CHAT_CONTEXT_EDIT_TRIGGER is overridden in this "
                    "environment; this test pins the SHIPPED default")
    reset_settings_cache()
    assert 0 < get_settings().chat_context_edit_trigger <= 120_000


# --- provenance -----------------------------------------------------------

def test_provenance_records_the_compaction_settings(compaction, monkeypatch):
    """A compacted run is not the same experiment as an uncompacted one."""
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    monkeypatch.setenv("SILICONCREW_COMMIT", "deadbeef")
    prov.repo_commit.cache_clear()

    compaction(100_000, keep=3)
    d = prov.collect_provenance(pdk="sky130hd").as_dict()
    assert d["context_edit"] == "clear_tool_uses:trigger=100000,keep=3"

    compaction(0)
    assert prov.collect_provenance().as_dict()["context_edit"] == "off"
    prov.repo_commit.cache_clear()


def test_provenance_context_edit_matches_the_middleware_actually_shipped(compaction):
    """The stamp is derived from the same settings the middleware is built from;
    this is the guard that keeps the two from drifting apart."""
    from langchain.agents.middleware import ContextEditingMiddleware

    import src.platform_engines.provenance as prov

    compaction(77_000, keep=2)
    edits = [
        e
        for mw in architect_middleware()
        if isinstance(mw, ContextEditingMiddleware)
        for e in mw.edits
    ]
    assert len(edits) == 1
    stamp = prov.context_edit_identity()
    assert f"trigger={edits[0].trigger}" in stamp
    assert f"keep={edits[0].keep}" in stamp


def test_a_bound_provenance_scope_is_read_not_recomposed(compaction):
    """The A3-H4 rule holds for the new field too: a worker reads the stamp the
    request scope resolved, it does not look the settings up again."""
    import src.platform_engines.provenance as prov

    compaction(100_000, keep=3)
    with prov.agent_provenance_scope(prov.AgentProvenance(context_edit="off")):
        assert prov.collect_provenance().as_dict()["context_edit"] == "off"
