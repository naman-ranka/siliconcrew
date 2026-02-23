import os
from typing import Any, AsyncIterator, Dict, Optional
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.tools.wrappers import architect_tools
from src.config import DEFAULT_MODEL
from .base import BaseRuntimeAdapter

class LangGraphAdapter(BaseRuntimeAdapter):
    def __init__(self, checkpointer=None, model_name=DEFAULT_MODEL, api_keys=None):
        self.model_name = model_name
        self.checkpointer = checkpointer

        # Gemini 3 models require special configuration for proper tool calling
        is_gemini_3 = "gemini-3" in model_name.lower()

        api_key = (api_keys or {}).get("google_api_key") or os.environ.get("GOOGLE_API_KEY")

        llm_kwargs = {
            "model": model_name,
            "google_api_key": api_key,
        }

        if is_gemini_3:
            import warnings
            warnings.warn(
                f"⚠️ {model_name} has known issues with LangChain's create_react_agent. "
                "You may experience empty responses. Consider using 'gemini-2.5-flash' instead.",
                UserWarning
            )
            llm_kwargs["temperature"] = 1.0
            llm_kwargs["include_thoughts"] = True

        llm = ChatGoogleGenerativeAI(**llm_kwargs)

        self.agent_graph = create_react_agent(
            model=llm,
            tools=architect_tools,
            checkpointer=checkpointer
        )

    async def aget_state(self, config: RunnableConfig) -> Any:
        # Delegate to internal graph
        return await self.agent_graph.aget_state(config)

    async def astream(
        self,
        input: Dict[str, Any],
        config: RunnableConfig,
        stream_mode: str = "updates",
    ) -> AsyncIterator[Any]:
        # Delegate to internal graph
        async for event in self.agent_graph.astream(input, config, stream_mode=stream_mode):
            yield event
