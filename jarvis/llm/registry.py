"""
Centralized Provider Registry for LLM Providers (Batch 20).
"""

import logging
import asyncio
from typing import Dict, List, Optional
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.exceptions import (
    ProviderNotFoundError,
    LLMConfigurationError,
)

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """
    Centralized registry managing provider instances, lifecycles, and lookups.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, AbstractLLMProvider] = {}
        self._lock = asyncio.Lock()

    def register_provider(self, provider: AbstractLLMProvider) -> None:
        """
        Registers an LLM provider. Rejects duplicate registrations.
        """
        if not provider or not provider.provider_id:
            raise LLMConfigurationError("Cannot register provider without valid provider_id.")

        pid = provider.provider_id.strip()
        if pid in self._providers:
            raise LLMConfigurationError(f"Duplicate LLM provider registration for '{pid}'.")

        self._providers[pid] = provider
        logger.info(f"LLMProviderRegistry: registered provider '{pid}' (local={provider.is_local}).")

    def unregister_provider(self, provider_id: str) -> Optional[AbstractLLMProvider]:
        """
        Unregisters a provider by ID if present.
        """
        pid = provider_id.strip()
        provider = self._providers.pop(pid, None)
        if provider:
            logger.info(f"LLMProviderRegistry: unregistered provider '{pid}'.")
        return provider

    def get_provider(self, provider_id: str) -> AbstractLLMProvider:
        """
        Retrieves a registered provider by ID. Raises ProviderNotFoundError if missing.
        """
        pid = provider_id.strip()
        provider = self._providers.get(pid)
        if not provider:
            raise ProviderNotFoundError(
                f"LLM Provider '{pid}' is not registered in LLMProviderRegistry.",
                provider_id=pid,
            )
        return provider

    def has_provider(self, provider_id: str) -> bool:
        """Returns True if provider_id is registered."""
        return provider_id.strip() in self._providers

    def list_providers(self) -> List[AbstractLLMProvider]:
        """Lists all currently registered providers."""
        return list(self._providers.values())

    async def close_all(self) -> None:
        """
        Gracefully closes all registered providers during runtime shutdown.
        """
        async with self._lock:
            for pid, provider in list(self._providers.items()):
                try:
                    await provider.close()
                    logger.info(f"LLMProviderRegistry: closed provider '{pid}'.")
                except Exception as ex:
                    logger.error(f"Error closing provider '{pid}' during shutdown: {ex}")
            self._providers.clear()
