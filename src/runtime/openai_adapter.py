import os
import json
from typing import Any, AsyncIterator, Dict, List, Literal
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
)
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from openai import AsyncOpenAI

from src.tools.wrappers import architect_tools
from src.config import DEFAULT_MODEL
from .base import BaseRuntimeAdapter, StateSnapshot

# Define State
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class OpenAIAdapter(BaseRuntimeAdapter):
    def __init__(self, checkpointer=None, model_name="gpt-4o"):
        self.checkpointer = checkpointer
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Convert tools to OpenAI format
        self.openai_tools = [convert_to_openai_tool(t) for t in architect_tools]

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
        openai_msgs = self._convert_messages(messages)

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=openai_msgs,
                tools=self.openai_tools,
                tool_choice="auto" if self.openai_tools else None
            )

            choice = response.choices[0]
            message_data = choice.message

            tool_calls = []
            if message_data.tool_calls:
                for tc in message_data.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments),
                        "id": tc.id
                    })

            ai_message = AIMessage(
                content=message_data.content or "",
                tool_calls=tool_calls,
                usage_metadata={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else None
            )

            return {"messages": [ai_message]}

        except Exception as e:
            return {"messages": [AIMessage(content=f"Error calling OpenAI: {str(e)}")]}

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

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict]:
        openai_msgs = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                openai_msgs.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                openai_msgs.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                msg_dict = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    tool_calls = []
                    for tc in msg.tool_calls:
                        tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"])
                            }
                        })
                    msg_dict["tool_calls"] = tool_calls
                openai_msgs.append(msg_dict)
            elif isinstance(msg, ToolMessage):
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content
                })
        return openai_msgs
