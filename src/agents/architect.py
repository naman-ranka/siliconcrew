"""
The Architect Agent - Production-grade RTL Design Agent

This module creates the main agent responsible for hardware design, verification,
and synthesis. Uses a ReAct pattern with comprehensive tool access.
"""

import os
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
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


def _strip_reasoning_blocks(state: dict) -> dict:
    """pre_model_hook: drop `thinking`/`redacted_thinking` content blocks from
    every message right before the LLM sees them (does NOT touch the
    checkpoint — only `llm_input_messages`, the model-facing view).

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
    """
    messages = state.get("messages", [])
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
    return {"llm_input_messages": cleaned if changed else messages}


def create_architect_agent(checkpointer=None, model_name=DEFAULT_MODEL, api_key=None):
    """
    Creates the Architect agent using ReAct pattern.

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
    # wrong kwarg and hand back an agent with NO prompt and NO pre-model hook —
    # a silently lobotomised agent that still answers, so nothing looks broken.
    # A signature mismatch is a wiring bug and must fail loudly at construction.
    agent_graph = create_react_agent(
        model=llm,
        tools=architect_tools,
        checkpointer=checkpointer,
        prompt=runtime_prompt,
        pre_model_hook=_strip_reasoning_blocks,
    )

    return agent_graph

