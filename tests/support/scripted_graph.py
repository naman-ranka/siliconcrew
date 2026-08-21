"""Build a REAL agent graph driven by a scripted model.

Every websocket test in this repo used to hand-construct the agent's output —
``yield ("updates", {"model": {...}})``. That asserts nothing about the
framework: the day LangGraph renames a node, the fakes keep yielding the old key
and the whole suite stays green while the product emits no text, no tool cards,
no activity rows and no token counts.

So: the MODEL is fake (scripted, deterministic, no network), the GRAPH is real.
Frames captured through this harness are evidence about the framework, not about
our fixtures.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from langchain.agents import create_agent

from src.agents.architect import architect_middleware


class ScriptedChatModel(BaseChatModel):
    """Returns queued AIMessages in order; repeats the last one if exhausted.

    Exhaustion repeats rather than raising on purpose — a recursion-limit
    scenario needs a model that will keep calling a tool forever.
    """

    script: List[AIMessage] = []
    calls: List[int] = []
    seen: List[List[BaseMessage]] = []
    """The message list handed to the model on each round, in order.

    Middleware that edits the model's VIEW without editing stored state (the
    reasoning strip, context compaction) is invisible from the checkpoint by
    design, so a test asserting "it fired" has nowhere else to look. Recorded
    here rather than reconstructed, because a reconstruction would assert the
    test's model of the middleware instead of the middleware.
    """

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        """The script decides what is called, so the bound tool list is ignored.

        Returning ``self`` keeps ``.calls`` shared with the caller, which is how
        a test counts model round-trips (needed for the recursion-budget check).
        """
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        idx = len(self.calls)
        self.calls.append(idx)
        self.seen.append(list(messages))
        msg = self.script[idx] if idx < len(self.script) else self.script[-1]
        # Fresh copy each call: LangGraph appends these to state, and a reused
        # object would alias across turns.
        return ChatResult(generations=[ChatGeneration(message=msg.model_copy(deep=True))])


def ai(content: str = "", tool_calls: Optional[Iterable[Dict[str, Any]]] = None,
       usage: Optional[Dict[str, int]] = None) -> AIMessage:
    kwargs: Dict[str, Any] = {"content": content}
    if tool_calls:
        kwargs["tool_calls"] = [
            {"id": tc["id"], "name": tc["name"], "args": tc.get("args", {}), "type": "tool_call"}
            for tc in tool_calls
        ]
    if usage:
        kwargs["usage_metadata"] = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }
    return AIMessage(**kwargs)


@tool
def echo_tool(text: str) -> str:
    """Echo the given text back. Test double, not a real SiliconCrew tool."""
    return f"echoed: {text}"


@tool
def exploding_tool(text: str) -> str:
    """Always raise. Test double for the tool-error frame path."""
    raise RuntimeError(f"boom: {text}")


def build_real_graph_with_model(script: List[AIMessage], tools=None, checkpointer=None):
    """A real ``create_agent`` graph over a scripted model, plus the model.

    Built with the SAME middleware list production ships, so the harness
    exercises the real hooks — a middleware that only implements the sync path
    would blow up here under ``astream`` exactly as it would in the product.

    The model comes back too because ``ScriptedChatModel.calls`` is how a test
    counts model round-trips, which is the only honest way to measure the step
    budget a turn actually gets at a given recursion limit.
    """
    model = ScriptedChatModel(script=script, calls=[], seen=[])
    graph = create_agent(
        model=model,
        tools=list(tools) if tools is not None else [echo_tool, exploding_tool],
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
        middleware=architect_middleware(),
    )
    return graph, model


def build_real_graph(script: List[AIMessage], tools=None, checkpointer=None):
    """A real ``create_agent`` graph over a scripted model."""
    return build_real_graph_with_model(script, tools=tools, checkpointer=checkpointer)[0]
