from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from langchain_core.runnables import RunnableConfig

class StateSnapshot:
    """Mock of LangGraph's StateSnapshot."""
    def __init__(self, values: Dict[str, Any]):
        self.values = values

class BaseRuntimeAdapter(ABC):
    """
    Abstract base class for agent runtime adapters.
    This defines the interface that api.py expects.
    """

    @abstractmethod
    async def aget_state(self, config: RunnableConfig) -> StateSnapshot:
        """
        Get the current state of the agent for the given config (thread_id).
        Returns an object with a .values dict containing "messages".
        """
        pass

    @abstractmethod
    async def astream(
        self,
        input: Dict[str, Any],
        config: RunnableConfig,
        stream_mode: str = "updates",
    ) -> AsyncIterator[Any]:
        """
        Stream events from the agent.
        Yields events in the format expected by api.py.
        """
        pass
