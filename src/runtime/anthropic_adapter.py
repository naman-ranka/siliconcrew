import os
import json
from typing import Any, AsyncIterator, Dict, List, Literal, Tuple
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from anthropic import AsyncAnthropic

from src.tools.wrappers import architect_tools
from src.config import DEFAULT_MODEL
from .base import BaseRuntimeAdapter, StateSnapshot

# Define State
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class AnthropicAdapter(BaseRuntimeAdapter):
    def __init__(self, checkpointer=None, model_name="claude-3-5-sonnet-20241022", api_keys=None):
        self.checkpointer = checkpointer
        self.model_name = model_name

        # Get key from args or env
        api_key = (api_keys or {}).get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(api_key=api_key)

        # Convert tools to Anthropic format
        self.anthropic_tools = [self._convert_tool(t) for t in architect_tools]

        # Build Graph
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tools", ToolNode(architect_tools))

        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")

        self.graph = workflow.compile(checkpointer=checkpointer)

    async def call_model(self, state: AgentState):
        messages = state["messages"]
        system_prompt, anthropic_msgs = self._convert_messages(messages)

        # Anthropic max_tokens is required
        kwargs = {
            "model": self.model_name,
            "messages": anthropic_msgs,
            "max_tokens": 4096,
            "tools": self.anthropic_tools
        }
        if system_prompt.strip():
            kwargs["system"] = system_prompt.strip()

        response = await self.client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "args": block.input,
                    "id": block.id
                })

        ai_message = AIMessage(
            content=content_text,
            tool_calls=tool_calls,
            usage_metadata={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            } if response.usage else None
        )

        return {"messages": [ai_message]}

    def should_continue(self, state: AgentState) -> Literal["tools", END]:
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    async def aget_state(self, config: RunnableConfig) -> Any:
        return await self.graph.aget_state(config)

    async def astream(
        self,
        input: Dict[str, Any],
        config: RunnableConfig,
        stream_mode: str = "updates",
    ) -> AsyncIterator[Any]:
        async for event in self.graph.astream(input, config, stream_mode=stream_mode):
            yield event

    def _convert_messages(self, messages: List[BaseMessage]) -> Tuple[str, List[Dict]]:
        system_prompt = ""
        anthropic_msgs = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_prompt += msg.content + "\n"
                continue

            role = "user"
            content_block = []

            if isinstance(msg, HumanMessage):
                role = "user"
                content_block.append({"type": "text", "text": msg.content})
            elif isinstance(msg, AIMessage):
                role = "assistant"
                if msg.content:
                    content_block.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content_block.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["args"]
                        })
                if not content_block:
                    content_block.append({"type": "text", "text": ""})

            elif isinstance(msg, ToolMessage):
                role = "user"
                content_block.append({
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content
                })

            # Merge with previous if same role (Anthropic requires alternating roles)
            if anthropic_msgs and anthropic_msgs[-1]["role"] == role:
                # Ensure previous content is a list
                if isinstance(anthropic_msgs[-1]["content"], str):
                    anthropic_msgs[-1]["content"] = [{"type": "text", "text": anthropic_msgs[-1]["content"]}]
                anthropic_msgs[-1]["content"].extend(content_block)
            else:
                anthropic_msgs.append({"role": role, "content": content_block})

        return system_prompt, anthropic_msgs

    def _convert_tool(self, tool):
        schema = tool.args_schema.schema() if tool.args_schema else {"type": "object", "properties": {}}
        # Clean up schema if needed (remove 'title', 'description' from properties?)
        # Anthropic is usually fine with standard JSON schema.
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": schema
        }
