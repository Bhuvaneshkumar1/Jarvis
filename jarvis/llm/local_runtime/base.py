"""
Abstract Local Inference Runtime Interface for JARVIS (Batch 23).
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from jarvis.llm.contracts import LLMRequest, LLMResponse, LLMStreamEvent


class AbstractLocalRuntime(ABC):
    """
    Abstract contract for local inference runtimes (e.g. llama.cpp, mock runtime).
    """

    @abstractmethod
    async def load_model(
        self,
        model_path: str,
        context_window: int = 2048,
        threads: int = 4,
        gpu_layers: int = 0,
    ) -> bool:
        """Loads GGUF model into local inference memory."""
        pass

    @abstractmethod
    async def unload_model(self) -> None:
        """Unloads GGUF model and releases system memory resources."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Returns True if a model is currently loaded in memory."""
        pass

    @abstractmethod
    def get_memory_usage_mb(self) -> float:
        """Returns current estimated memory consumption in MB."""
        pass

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Executes synchronous local inference."""
        pass

    @abstractmethod
    def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Executes streaming local inference yielding LLMStreamEvents."""
        pass
