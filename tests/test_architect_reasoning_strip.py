"""pre_model_hook strips thinking/redacted_thinking content blocks from every
message before the LLM sees them (does not touch the checkpoint).

Root cause this guards against: a thread's history can carry a reasoning
content block shaped by one provider (or an older/newer SDK version) that a
DIFFERENT provider's strict request validation rejects outright — observed as
Anthropic 400 'messages.N.content.0.thinking.thinking: Field required' when a
thread that had prior turns on another model is continued on Claude. Since
tool-calling correctness lives in `.tool_calls`, not `.content`, dropping
reasoning blocks before every model call is safe and self-heals any thread
already stuck on a bad historical block — no checkpoint migration needed.
"""
from typing import Any, List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from src.agents.architect import _strip_reasoning_blocks


def _msg(content):
    return AIMessage(content=content)


def test_strips_thinking_and_redacted_thinking_blocks():
    history = [
        HumanMessage(content="hi"),
        _msg([{"type": "thinking", "thinking": ""}, {"type": "text", "text": "hello"}]),
        _msg([{"type": "redacted_thinking", "data": "xyz"}, {"type": "text", "text": "ok"}]),
    ]
    out = _strip_reasoning_blocks({"messages": history})
    llm_messages = out["llm_input_messages"]
    assert llm_messages[0] is history[0]  # untouched HumanMessage passes through
    assert llm_messages[1].content == [{"type": "text", "text": "hello"}]
    assert llm_messages[2].content == [{"type": "text", "text": "ok"}]


def test_malformed_thinking_block_missing_required_field_is_still_stripped():
    # The exact failure shape from the field-required 400: a "thinking" block
    # present but missing its own "thinking" text — stripped regardless of
    # whether the block is well-formed, since we never resend the type at all.
    history = [_msg([{"type": "thinking"}, {"type": "text", "text": "hi"}])]
    out = _strip_reasoning_blocks({"messages": history})
    assert out["llm_input_messages"][0].content == [{"type": "text", "text": "hi"}]


def test_no_op_when_no_reasoning_blocks_present():
    history = [HumanMessage(content="hi"), _msg("plain string content")]
    out = _strip_reasoning_blocks({"messages": history})
    # Unmodified — same objects, not copies, when nothing needed stripping.
    assert out["llm_input_messages"] is history


def test_checkpoint_keeps_original_while_model_never_sees_the_bad_block():
    """End-to-end: a corrupted historical message survives in the checkpoint
    (for token accounting / display) but the LLM itself never receives it —
    proving self-healing without a checkpoint migration."""

    class _RecordingModel(BaseChatModel):
        seen: List[List[BaseMessage]] = []

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            self.seen.append(list(messages))
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="reply"))])

        @property
        def _llm_type(self) -> str:
            return "recording-fake"

    model = _RecordingModel()
    checkpointer = InMemorySaver()
    graph = create_react_agent(
        model=model, tools=[], checkpointer=checkpointer, pre_model_hook=_strip_reasoning_blocks,
    )
    config = {"configurable": {"thread_id": "t1"}}

    # Seed a corrupted historical assistant message directly into the checkpoint,
    # simulating a thread that already has a bad block from a prior turn/provider.
    graph.update_state(config, {"messages": [
        HumanMessage(content="earlier turn"),
        _msg([{"type": "thinking"}, {"type": "text", "text": "earlier reply"}]),
    ]})

    graph.invoke({"messages": [HumanMessage(content="continue")]}, config)

    # The model's actual input never contained a thinking-type block.
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
    snapshot = graph.get_state(config)
    checkpointed = snapshot.values["messages"]
    assert any(
        isinstance(m.content, list)
        and any(isinstance(b, dict) and b.get("type") == "thinking" for b in m.content)
        for m in checkpointed
    )
