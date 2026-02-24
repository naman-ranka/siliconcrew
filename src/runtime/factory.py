from typing import Optional
from .base import BaseRuntimeAdapter
from .langgraph_adapter import LangGraphAdapter
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter
from src.auth.manager import AuthManager

class RuntimeFactory:
    @staticmethod
    async def aget_runtime(model_name: str, checkpointer=None, api_keys=None, db_path=None) -> BaseRuntimeAdapter:
        """
        Returns the appropriate runtime adapter for the given model.
        Resolves authentication tokens using AuthManager if explicit api_keys are not provided.
        """

        # Resolve keys if not provided explicitly
        resolved_keys = api_keys or {}
        auth_manager = AuthManager(db_path=db_path)

        # Determine provider and resolve ONLY the needed key
        if model_name.startswith("gpt-") or model_name.startswith("o1") or model_name.startswith("o3"):
            if "openai_api_key" not in resolved_keys:
                token = await auth_manager.aget_token("openai")
                if token:
                    resolved_keys["openai_api_key"] = token
            return OpenAIAdapter(checkpointer=checkpointer, model_name=model_name, api_keys=resolved_keys)

        elif model_name.startswith("claude-"):
            if "anthropic_api_key" not in resolved_keys:
                token = await auth_manager.aget_token("anthropic")
                if token:
                    resolved_keys["anthropic_api_key"] = token
            return AnthropicAdapter(checkpointer=checkpointer, model_name=model_name, api_keys=resolved_keys)

        else:
            # Default to LangGraph (Gemini)
            if "google_api_key" not in resolved_keys:
                token = await auth_manager.aget_token("gemini")
                if token:
                    resolved_keys["google_api_key"] = token
            return LangGraphAdapter(checkpointer=checkpointer, model_name=model_name, api_keys=resolved_keys)
