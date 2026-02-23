from typing import Optional
from .base import BaseRuntimeAdapter
from .langgraph_adapter import LangGraphAdapter
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

class RuntimeFactory:
    @staticmethod
    def get_runtime(model_name: str, checkpointer=None) -> BaseRuntimeAdapter:
        """
        Returns the appropriate runtime adapter for the given model.
        """
        if model_name.startswith("gpt-"):
            return OpenAIAdapter(checkpointer=checkpointer, model_name=model_name)
        elif model_name.startswith("claude-"):
            return AnthropicAdapter(checkpointer=checkpointer, model_name=model_name)
        else:
            # Default to LangGraph (Gemini)
            return LangGraphAdapter(checkpointer=checkpointer, model_name=model_name)
