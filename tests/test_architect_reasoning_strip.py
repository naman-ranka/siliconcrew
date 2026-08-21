"""The reasoning-strip middleware drops thinking/redacted_thinking content
blocks from every message before the LLM sees them (does not touch the
checkpoint).

Root cause this guards against: a thread's history can carry a reasoning
content block shaped by one provider (or an older/newer SDK version) that a
DIFFERENT provider's strict request validation rejects outright — observed as
Anthropic 400 'messages.N.content.0.thinking.thinking: Field required' when a
thread that had prior turns on another model is continued on Claude. Since
tool-calling correctness lives in `.tool_calls`, not `.content`, dropping
reasoning blocks before every model call is safe and self-heals any thread
already stuck on a bad historical block — no checkpoint migration needed.

The strip used to be a ``pre_model_hook`` returning ``llm_input_messages``; it
is now a ``wrap_model_call`` middleware overriding ``request.messages``. Both
are model-facing-only, and the property that matters is asserted end to end
below: the bad block stays in the checkpoint and never reaches the model.
"""
import asyncio
from typing import List

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.architect import (
    ReasoningStripMiddleware,
    _model_facing_messages,
    architect_middleware,
)


def _msg(content):
    return AIMessage(content=content)


def test_strips_thinking_and_redacted_thinking_blocks():
    history = [
        HumanMessage(content="hi"),
        _msg([{"type": "thinking", "thinking": ""}, {"type": "text", "text": "hello"}]),
        _msg([{"type": "redacted_thinking", "data": "xyz"}, {"type": "text", "text": "ok"}]),
    ]
    cleaned, changed = _model_facing_messages(history)
    assert changed
    assert cleaned[0] is history[0]  # untouched HumanMessage passes through
    assert cleaned[1].content == [{"type": "text", "text": "hello"}]
    assert cleaned[2].content == [{"type": "text", "text": "ok"}]


def test_malformed_thinking_block_missing_required_field_is_still_stripped():
    # The exact failure shape from the field-required 400: a "thinking" block
    # present but missing its own "thinking" text — stripped regardless of
    # whether the block is well-formed, since we never resend the type at all.
    history = [_msg([{"type": "thinking"}, {"type": "text", "text": "hi"}])]
    cleaned, changed = _model_facing_messages(history)
    assert changed
    assert cleaned[0].content == [{"type": "text", "text": "hi"}]


def test_no_op_when_no_reasoning_blocks_present():
    history = [HumanMessage(content="hi"), _msg("plain string content")]
    cleaned, changed = _model_facing_messages(history)
    # Unmodified — same list, not copies, when nothing needed stripping. The
    # middleware skips `request.override` entirely in that case.
    assert changed is False
    assert cleaned is history


# --- the stored prompt ------------------------------------------------------
# A thread started before the prompt moved into `create_agent(system_prompt=)`
# carries a SystemMessage of its own in the checkpoint. Left alone, the model
# receives that prompt AND today's — two sets of instructions that contradict
# each other, since the old one prescribed a fixed flow the new one drops on
# purpose. Every future prompt revision would repeat it, so the strip is
# permanent rather than a one-off migration.

def test_a_stored_system_prompt_is_dropped_from_the_model_view():
    history = [
        SystemMessage(content="OLD 128-LINE PROMPT: always execute the full flow"),
        HumanMessage(content="hi"),
    ]
    cleaned, changed = _model_facing_messages(history)
    assert changed
    assert [type(m).__name__ for m in cleaned] == ["HumanMessage"]


def test_the_architect_ships_the_strip_middleware():
    """It must stay unconditional: it is the thing that makes switching models
    mid-thread safe, and it self-heals threads a PREVIOUS model corrupted."""
    assert any(isinstance(mw, ReasoningStripMiddleware) for mw in architect_middleware())


class _RecordingModel(BaseChatModel):
    seen: List[List[BaseMessage]] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="reply"))])

    @property
    def _llm_type(self) -> str:
        return "recording-fake"


def _seeded_graph(model):
    checkpointer = InMemorySaver()
    graph = create_agent(
        model=model, tools=[], checkpointer=checkpointer,
        middleware=[ReasoningStripMiddleware()],
    )
    config = {"configurable": {"thread_id": "t1"}}
    # Seed a corrupted historical assistant message directly into the checkpoint,
    # simulating a thread that already has a bad block from a prior turn/provider.
    graph.update_state(config, {"messages": [
        HumanMessage(content="earlier turn"),
        _msg([{"type": "thinking"}, {"type": "text", "text": "earlier reply"}]),
    ]})
    return graph, config


def _assert_stripped_but_checkpointed(model, graph, config):
    all_seen_blocks = [
        block
        for call in model.seen
        for msg in call
        if isinstance(msg.content, list)
        for block in msg.content
    ]
    assert not any(
        isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
        for b in all_seen_blocks
    ), all_seen_blocks

    # But the checkpoint still has the original block (nothing was migrated/mutated).
    checkpointed = graph.get_state(config).values["messages"]
    assert any(
        isinstance(m.content, list)
        and any(isinstance(b, dict) and b.get("type") == "thinking" for b in m.content)
        for m in checkpointed
    )


def test_checkpoint_keeps_original_while_model_never_sees_the_bad_block_async():
    """End-to-end on the path the product actually uses (``astream``).

    A sync-only ``wrap_model_call`` raises NotImplementedError here, which is
    precisely the trap this test exists to keep sprung.
    """
    model = _RecordingModel()
    graph, config = _seeded_graph(model)

    async def run():
        async for _ in graph.astream({"messages": [HumanMessage(content="continue")]}, config):
            pass

    asyncio.run(run())
    _assert_stripped_but_checkpointed(model, graph, config)


def test_a_thread_started_on_the_old_prompt_gets_exactly_one_prompt():
    """End to end: an existing thread's stored prompt stays in the checkpoint
    (nothing is migrated or lost) and the model is sent today's prompt, once."""
    model = _RecordingModel()
    checkpointer = InMemorySaver()
    graph = create_agent(
        model=model, tools=[], checkpointer=checkpointer,
        system_prompt="TODAY'S PROMPT",
        middleware=[ReasoningStripMiddleware()],
    )
    config = {"configurable": {"thread_id": "old-thread"}}
    graph.update_state(config, {"messages": [
        SystemMessage(content="YESTERDAY'S PROMPT"),
        HumanMessage(content="earlier turn"),
        AIMessage(content="earlier reply"),
    ]})

    graph.invoke({"messages": [HumanMessage(content="continue")]}, config)

    sent = model.seen[-1]
    prompts = [m for m in sent if isinstance(m, SystemMessage)]
    assert [m.content for m in prompts] == ["TODAY'S PROMPT"]
    # ...and the thread's own history is untouched.
    stored = graph.get_state(config).values["messages"]
    assert any(isinstance(m, SystemMessage) and "YESTERDAY" in m.content for m in stored)
    # The user's turns still reach the model — only the prompt was removed.
    assert any(isinstance(m, HumanMessage) and m.content == "earlier turn" for m in sent)


def test_the_turn_driver_writes_no_system_message_into_new_threads():
    """The other half: a new thread must not store a prompt either, or the same
    contradiction is recreated on the next prompt revision."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "api.py"), encoding="utf-8-sig") as fh:
        source = fh.read()
    assert "input_messages.append(SystemMessage(" not in source


def test_checkpoint_keeps_original_while_model_never_sees_the_bad_block_sync():
    """Same property on the SYNC path. LangChain raises NotImplementedError when
    a turn takes the hook you did not define, so the middleware implements both
    and this test proves the sync half is really there — the repo holds graphs
    outside the websocket (``src/utils/reporter.py``)."""
    model = _RecordingModel()
    graph, config = _seeded_graph(model)
    graph.invoke({"messages": [HumanMessage(content="continue")]}, config)
    _assert_stripped_but_checkpointed(model, graph, config)
