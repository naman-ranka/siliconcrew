"""
The Architect Agent - Production-grade RTL Design Agent

This module creates the main agent responsible for hardware design, verification,
and synthesis. Uses a ReAct pattern with comprehensive tool access.
"""

import os
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
)
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


def _model_facing_messages(messages):
    """Return (messages, changed) with `thinking`/`redacted_thinking` content
    blocks dropped, and any STORED system message removed. Copies only the
    messages that actually needed a change.

    Why system messages go too: the running prompt is delivered as
    `create_agent(system_prompt=...)`, which arrives as its own request field,
    while a thread started before that carries a SystemMessage of its own inside
    the checkpoint. The model then receives two prompts — the current one and a
    128-line predecessor that prescribes a fixed flow the current one
    deliberately dropped — and follows whichever it likes. Every future prompt
    revision would repeat this on every existing thread, so the fix belongs
    here, on the model-facing view, not in a one-off migration: the checkpoint
    keeps its history and the model is sent exactly one prompt, today's.
    """
    cleaned = []
    changed = False
    for msg in messages:
        if isinstance(msg, SystemMessage):
            changed = True
            continue
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
    """Drop `thinking`/`redacted_thinking` content blocks — and any stored
    system prompt — from every message right before the LLM sees them. The
    checkpoint is NOT touched: this rewrites only the model-facing view of the
    messages.

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
        messages, changed = _model_facing_messages(request.messages)
        return handler(request.override(messages=messages) if changed else request)

    async def awrap_model_call(self, request, handler):
        messages, changed = _model_facing_messages(request.messages)
        return await handler(request.override(messages=messages) if changed else request)


def context_compaction_middleware():
    """Keep a long design session inside the model's context window.

    A chip design session is long by nature — spec, RTL, lint, several
    simulation rounds, a synthesis run, then debugging — and nothing used to
    trim it, so a thread simply grew until the provider refused it. The user
    hit that wall at the deepest point of their work, and the only recovery was
    to start a new session and lose the thread.

    What this does, and just as importantly what it does NOT do
    -----------------------------------------------------------
    Once the message list crosses the trigger, the CONTENT of every tool result
    except the most recent few is replaced with ``[cleared]`` — in a deep copy
    handed to the model. Nothing is removed and nothing is stored:
    ``ContextEditingMiddleware`` is a ``wrap_model_call`` hook, so it never
    produces a state update and the checkpoint is left content-identical
    (verified against a real AsyncSqliteSaver, and pinned by
    ``tests/test_context_compaction.py``).

    That distinction is the whole point of this being its own change. The
    checkpoint IS the user's chat transcript — ``api._read_thread_history``
    rebuilds the panel from it and there is no ``messages`` table behind it — so
    a summarizing middleware, which rewrites the stored list and drops the
    user's own turns, would not be compaction but silent, unrecoverable data
    loss. ``SummarizationMiddleware`` was probed and refused for exactly that.

    Why clearing OLD TOOL RESULTS is the honest thing to drop: they are the only
    part of the history that is reproducible. The workspace and the run
    directory are the sources of truth, so a cleared ``read_file`` or
    ``get_synthesis_status`` is one tool call away from being recovered, and an
    old one describes a state that has since moved anyway. The user's words and
    the model's own reasoning are not reproducible, and are never touched.

    Pairing safety: a model request carrying a tool call whose result is missing
    is a provider 400. This strategy edits content in place and never removes a
    message, so a call and its result cannot be separated regardless of where
    the retention boundary falls — it is structural, not bookkeeping. It also
    composes with the start-of-turn dangling-call repair in ``api.py``, which
    reads the CHECKPOINT (untouched here) to find calls an interrupted run left
    open.

    Token counting is the local ``chars/4`` approximation on purpose:
    ``token_count_method="model"`` would put a provider round-trip in front of
    every model call.

    Returns an empty list when the trigger is 0, so compaction is one env var
    away from being off.
    """
    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if settings.chat_context_edit_trigger <= 0:
        return []
    return [
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=settings.chat_context_edit_trigger,
                    keep=settings.chat_context_edit_keep,
                )
            ],
            token_count_method="approximate",
        )
    ]


def architect_middleware():
    """The middleware the architect ships, in order.

    Order is outermost-first for the wrap hooks, so the reasoning strip runs
    before compaction: compaction then counts tokens on the message list the
    model will really be sent, rather than on blocks that were about to be
    dropped anyway.

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
       usage summed into the turn totals. ``ContextEditingMiddleware`` is clean
       on this point: with approximate counting it holds no model at all, and
       with model counting it would borrow the REQUEST's model, never its own.
    """
    return [ReasoningStripMiddleware(), *context_compaction_middleware()]


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
