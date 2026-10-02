"""
LLM Provider Factory & Typed Configuration Validation (Batch 20).
"""

import os
import logging
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field

from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.exceptions import LLMConfigurationError
from jarvis.core.secrets import SecretsManager

logger = logging.getLogger(__name__)


class LLMProviderConfig(BaseModel):
    enabled: bool = Field(default=False)
    api_key_name: Optional[str] = Field(default=None)
    endpoint_url: Optional[str] = Field(default=None)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=128000)
    extra_options: Dict[str, Any] = Field(default_factory=dict)


class LLMSubsystemConfig(BaseModel):
    default_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    default_max_output_tokens: int = Field(default=2048, ge=1, le=128000)
    providers: Dict[str, LLMProviderConfig] = Field(
        default_factory=lambda: {
            "nvidia": LLMProviderConfig(enabled=False, api_key_name="NVIDIA_API_KEY"),
            "openrouter": LLMProviderConfig(enabled=False, api_key_name="OPENROUTER_API_KEY"),
            "local": LLMProviderConfig(enabled=False, endpoint_url="http://localhost:11434"),
            "test_deterministic": LLMProviderConfig(enabled=True),
        }
    )


class LLMProviderFactory:
    """
    Factory instantiating and configuring LLM providers from validated settings.
    """

    def __init__(
        self,
        registry: LLMProviderRegistry,
        secrets_manager: Optional[SecretsManager] = None,
    ) -> None:
        self.registry = registry
        self.secrets_manager = secrets_manager
        self._provider_classes: Dict[str, Type[AbstractLLMProvider]] = {}

        # Register standard provider classes
        from jarvis.llm.providers.nvidia import NVIDIAProvider
        from jarvis.llm.providers.openrouter import OpenRouterProvider

        self.register_provider_class("nvidia", NVIDIAProvider)
        self.register_provider_class("openrouter", OpenRouterProvider)

    def register_provider_class(self, provider_id: str, provider_cls: Type[AbstractLLMProvider]) -> None:
        """Registers a provider class for factory instantiation."""
        pid = provider_id.strip()
        if pid in self._provider_classes:
            raise LLMConfigurationError(f"Duplicate factory registration for provider_id '{pid}'.")
        self._provider_classes[pid] = provider_cls

    def resolve_api_key(self, config: LLMProviderConfig) -> Optional[str]:
        """Resolves provider credentials safely without embedding in config files."""
        if not config.api_key_name:
            return None

        # 1. Check SecretsManager if available
        if self.secrets_manager:
            try:
                from jarvis.core.secrets.models import SecretAccessRequest

                sec_req = SecretAccessRequest(
                    requester="llm_factory",
                    secret_identifier=config.api_key_name,
                    purpose="resolve_api_key",
                )
                access_res = self.secrets_manager.get_secret(sec_req)
                if access_res.allowed and access_res.secret_value:
                    return access_res.secret_value.get_unredacted_value()
            except Exception:
                pass

        # 2. Check Environment variables
        env_val = os.environ.get(config.api_key_name)
        if env_val:
            return env_val

        return None

    def initialize_from_config(self, subsystem_config: LLMSubsystemConfig) -> None:
        """
        Instantiates and registers enabled providers according to subsystem_config.
        Does NOT instantiate or require credentials for disabled providers.
        """
        for pid, pconfig in subsystem_config.providers.items():
            if not pconfig.enabled:
                logger.info(f"LLMProviderFactory: provider '{pid}' is disabled in configuration. Skipping.")
                continue

            provider_cls = self._provider_classes.get(pid)
            if not provider_cls:
                logger.warning(f"LLMProviderFactory: enabled provider '{pid}' has no registered implementation class. Skipping.")
                continue

            # Validate credentials if required by cloud provider
            api_key = self.resolve_api_key(pconfig)

            try:
                # Instantiate provider with validated configuration
                instance = provider_cls(
                    provider_id=pid,
                    config=pconfig,  # type: ignore[call-arg]
                    api_key=api_key,  # type: ignore[call-arg]
                )
                self.registry.register_provider(instance)
            except Exception as ex:
                raise LLMConfigurationError(f"Failed to instantiate LLM provider '{pid}': {ex}") from ex
