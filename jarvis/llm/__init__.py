"""
LLM Provider Abstraction Subsystem for JARVIS AI OS (Batch 20).
"""

from jarvis.llm.exceptions import (
    LLMError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderConnectionError,
    ProviderResponseError,
    InvalidLLMRequestError,
    UnsupportedCapabilityError,
    ContextLengthExceededError,
    ContentFilteredError,
    LLMStreamInterruptedError,
    LLMConfigurationError,
    LLMInternalError,
    LLMPrivacyViolationError,
)
from jarvis.llm.contracts import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMRequestContract,
    LLMResponseContract,
    LLMStreamEvent,
    StreamEventType,
    LLMUsage,
    LLMToolCall,
    ModelCapability,
    DataClassification,
    LLMProviderState,
)
from jarvis.llm.privacy import LLMPrivacyEnforcer
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.factory import (
    LLMProviderConfig,
    LLMSubsystemConfig,
    LLMProviderFactory,
)
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.providers.nvidia import NVIDIAProvider
from jarvis.llm.providers.openrouter import OpenRouterProvider

__all__ = [
    "LLMError",
    "ProviderNotFoundError",
    "ProviderUnavailableError",
    "ProviderAuthenticationError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderConnectionError",
    "ProviderResponseError",
    "InvalidLLMRequestError",
    "UnsupportedCapabilityError",
    "ContextLengthExceededError",
    "ContentFilteredError",
    "LLMStreamInterruptedError",
    "LLMConfigurationError",
    "LLMInternalError",
    "LLMPrivacyViolationError",
    "ChatMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMRequestContract",
    "LLMResponseContract",
    "LLMStreamEvent",
    "StreamEventType",
    "LLMUsage",
    "LLMToolCall",
    "ModelCapability",
    "DataClassification",
    "LLMProviderState",
    "LLMPrivacyEnforcer",
    "AbstractLLMProvider",
    "LLMProviderRegistry",
    "LLMProviderConfig",
    "LLMSubsystemConfig",
    "LLMProviderFactory",
    "TestDeterministicLLMProvider",
    "NVIDIAProvider",
    "OpenRouterProvider",
]
