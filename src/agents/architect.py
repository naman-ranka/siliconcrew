"""
The Architect Agent - Production-grade RTL Design Agent

This module creates the main agent responsible for hardware design, verification,
and synthesis. Uses a ReAct pattern with comprehensive tool access.
"""

import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from pathlib import Path
from src.tools.wrappers import architect_tools
from src.config import DEFAULT_MODEL
from src.llm import create_llm

load_dotenv()

# =============================================================================
# SYSTEM PROMPT - Production Grade
# =============================================================================

# The 520-line embedded SYSTEM_PROMPT that used to live here is GONE.
# It was a fallback that went live on any prompt-file read failure, and it had
# drifted years out of date: a workflow that no longer applies, 58 tool names
# including several that no longer exist, and a utilization default the rest of
# the system had already moved off. A fallback nobody reads is a landmine that
# arms itself during an incident. Prompt resolution now lives in
# src.utils.architect_prompt and fails loudly.


# One implementation, shared with mcp_server, which needs it without paying
# LangGraph's import cost. These names stay exported here because callers and
# tests already reach for them at this path.
from src.utils.architect_prompt import (  # noqa: E402
    PromptUnavailable,
    load_system_prompt,
    prompt_path,
    resolved_version,
)

DEFAULT_ARCHITECT_PROMPT_VERSION = resolved_version()
PROMPT_FILE_DEFAULT = prompt_path()


# =============================================================================
# GRAPH NODE NAMES — the seam between this module and the turn driver
# =============================================================================
#
# `api.py`'s turn driver dispatches on the node names LangGraph puts in the
# `updates` stream and in `metadata["langgraph_node"]`. That coupling is real
# and it is silent: point it at the wrong name and the turn still runs and
# still checkpoints, but the socket emits no text, no tool cards, no activity
# rows and no token counts. The user sees a spinner and then nothing.
#
# The framework already moved these names once — `create_react_agent` called
# the model node "agent", `create_agent` calls it "model" — so the names live
# HERE, next to the factory that builds the graph, and every consumer imports
# them. `tests/test_ws_golden_frames.py` asserts the compiled graph's real node
# set against these constants, so a future framework rename fails a test
# instead of failing production.
MODEL_NODE = "model"
TOOLS_NODE = "tools"


def _without_reasoning_blocks(messages):
    """Return (messages, changed) with `thinking`/`redacted_thinking` content
    blocks dropped. Copies only the messages that actually needed a change."""
    cleaned = []
    changed = False
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            kept = [
                block for block in content
                if not (isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"))
            ]
            if len(kept) != len(content):
                msg = msg.model_copy(update={"content": kept})
                changed = True
        cleaned.append(msg)
    return (cleaned, True) if changed else (messages, False)


class ReasoningStripMiddleware(AgentMiddleware):
    """Drop `thinking`/`redacted_thinking` content blocks from every message
    right before the LLM sees them. The checkpoint is NOT touched — this
    rewrites only the model-facing view of the messages.

    Reasoning blocks are provider- and often model-version-specific. A thread
    can switch models mid-conversation (the picker allows it per turn), so a
    history built on one provider/model may carry a reasoning block shape the
    CURRENT provider's strict request validation rejects outright — e.g.
    Anthropic returning 400 "messages.N.content.0.thinking.thinking: Field
    required" when replaying a block that isn't a well-formed Anthropic
    thinking block. Our agent doesn't depend on reasoning traces surviving
    across turns (tool-calling correctness lives in `.tool_calls`, not
    `.content`), so the safe fix is: never resend them, from anyone, ever.
    This also self-heals a thread already stuck on a bad historical block —
    every future call strips it, no checkpoint migration required.

    Why `wrap_model_call` and not `before_model`: a `before_model` hook returns
    a state update, and the `messages` reducer is `add_messages`, so returning
    copies carrying the same ids would OVERWRITE the checkpoint — exactly what
    the paragraph above says must not happen. `wrap_model_call` also costs no
    graph step, where a node-style hook costs one per model call and quietly
    shrinks the per-turn budget (see CHAT_RECURSION_LIMIT in settings.py).

    Both the sync and async hooks are implemented on purpose. LangChain raises
    NotImplementedError when a turn takes the path you did not define, and this
    repo has graph consumers on both sides — `api.py` streams with `astream`,
    `src/utils/reporter.py` holds a graph and calls sync methods on it.
    """

    def wrap_model_call(self, request, handler):
        messages, changed = _without_reasoning_blocks(request.messages)
        return handler(request.override(messages=messages) if changed else request)

    async def awrap_model_call(self, request, handler):
        messages, changed = _without_reasoning_blocks(request.messages)
        return await handler(request.override(messages=messages) if changed else request)


def architect_middleware():
    """The middleware the architect ships, in order.

    Two rules this list is held to, both enforced by tests:

    1. **Prefer `wrap_model_call` over node-style hooks.** Node-style middleware
       (`before_model` / `after_model` / `before_agent` / `after_agent`) each
       consume one graph step per model call, so each one silently shrinks how
       much work a turn can do at a fixed recursion limit. Wrap-style hooks are
       free. Adding a node-style middleware means re-deriving
       CHAT_RECURSION_LIMIT in the same commit.
    2. **No middleware owns a model.** `SummarizationMiddleware(model=...)`,
       `ModelFallbackMiddleware` and friends construct their own LLM, which
       bypasses the request-scoped key resolution in `api.py`, the hosted model
       pin, cost accounting and the hosted-tier spend limiter — an uncapped
       BYOK/free-tier hole. If one is ever needed, it must be built from the
       same `create_llm(model_name, api_key=...)` call as the main model and its
       usage summed into the turn totals.
    """
    return [ReasoningStripMiddleware()]


def create_architect_agent(checkpointer=None, model_name=DEFAULT_MODEL, api_key=None):
    """
    Creates the Architect agent using LangChain's `create_agent`.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence
        model_name: Name of the LLM model to use
        api_key: Optional request-scoped LLM key (BYOK / hosted tier). When None,
            create_llm falls back to the environment key (self-host behavior).

    Returns:
        Compiled LangGraph agent
    """
    llm = create_llm(model_name=model_name, temperature=0.0, api_key=api_key)
    runtime_prompt = load_system_prompt()

    # NO try/except TypeError fallback here, deliberately. It used to swallow any
    # wrong kwarg and hand back an agent with NO prompt and NO reasoning strip —
    # a silently lobotomised agent that still answers, so nothing looks broken.
    # A signature mismatch is a wiring bug and must fail loudly at construction.
    agent_graph = create_agent(
        model=llm,
        tools=architect_tools,
        checkpointer=checkpointer,
        system_prompt=runtime_prompt,
        middleware=architect_middleware(),
    )

    return agent_graph
