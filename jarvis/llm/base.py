"""
Abstract LLM Provider Base Class & Model Capability Enforcer (Batch 20).
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator

from jarvis.core.enums import HealthState
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelCapability,
    LLMProviderState,
)
from jarvis.llm.exceptions import (
    ProviderUnavailableError,
    UnsupportedCapabilityError,
    ContextLengthExceededError,
)
from jarvis.llm.privacy import LLMPrivacyEnforcer

logger = logging.getLogger(__name__)


class AbstractLLMProvider(ABC):
    """
    Abstract Base Class defining the unified contract for all JARVIS LLM providers.
    """

    def __init__(
        self,
        provider_id: str,
        is_local: bool = False,
        privacy_enforcer: Optional[LLMPrivacyEnforcer] = None,
    ) -> None:
        self.provider_id = provider_id
        self.is_local = is_local
        self.state = LLMProviderState.NOT_INITIALIZED
        self.privacy_enforcer = privacy_enforcer or LLMPrivacyEnforcer()

    @abstractmethod
    async def initialize(self) -> None:
        """Initializes provider resources, connections, and authentication checks."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Closes active provider connections and cleans up allocated resources."""
        pass

    @abstractmethod
    async def health_check(self) -> HealthState:
        """Performs a lightweight provider health check without triggering generation requests."""
        pass

    @abstractmethod
    async def list_models(self) -> List[ModelCapability]:
        """Lists all models and capability profiles supported by this provider."""
        pass

    @abstractmethod
    async def get_capabilities(self, model_id: str) -> ModelCapability:
        """Retrieves capability details for a specific model."""
        pass

    @abstractmethod
    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        """Internal provider implementation of text generation."""
        pass

    @abstractmethod
    def _do_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Internal provider implementation of streaming response generation."""
        pass

    def validate_request_against_capabilities(self, request: LLMRequest, capability: ModelCapability) -> None:
        """
        Validates request parameter compatibility against model capability declaration.
        Raises UnsupportedCapabilityError or ContextLengthExceededError if invalid.
        """
        if request.stream and not capability.supports_streaming:
            raise UnsupportedCapabilityError(
                f"Model '{request.model_id}' does not support streaming.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        if request.response_format and not capability.supports_structured_output:
            raise UnsupportedCapabilityError(
                f"Model '{request.model_id}' does not support structured JSON output formatting.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        if request.tools and not capability.supports_tool_calling:
            raise UnsupportedCapabilityError(
                f"Model '{request.model_id}' does not support tool/function calling.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        if request.max_tokens and request.max_tokens > capability.max_output_tokens:
            raise ContextLengthExceededError(
                f"Requested max_tokens ({request.max_tokens}) exceeds model output cap ({capability.max_output_tokens}).",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Public entrypoint for non-streaming generation with validation, timeout, and privacy checks.
        """
        if self.state not in (LLMProviderState.READY, LLMProviderState.DEGRADED):
            raise ProviderUnavailableError(
                f"Provider '{self.provider_id}' is not in READY state (current: {self.state.value}).",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        capability = await self.get_capabilities(request.model_id)
        self.validate_request_against_capabilities(request, capability)

        # Enforce Privacy & Data Classification Policy
        sanitized_request = self.privacy_enforcer.validate_and_sanitize_request(request, is_local_provider=self.is_local)

        # Enforce request timeout
        try:
            return await asyncio.wait_for(
                self._do_generate(sanitized_request),
                timeout=sanitized_request.timeout,
            )
        except asyncio.TimeoutError:
            from jarvis.llm.exceptions import ProviderTimeoutError

            raise ProviderTimeoutError(
                f"Generation request timed out after {sanitized_request.timeout}s.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
                timeout_seconds=sanitized_request.timeout,
            )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """
        Public entrypoint for streaming generation with validation and privacy checks.
        """
        if self.state not in (LLMProviderState.READY, LLMProviderState.DEGRADED):
            raise ProviderUnavailableError(
                f"Provider '{self.provider_id}' is not in READY state (current: {self.state.value}).",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        capability = await self.get_capabilities(request.model_id)
        self.validate_request_against_capabilities(request, capability)

        sanitized_request = self.privacy_enforcer.validate_and_sanitize_request(request, is_local_provider=self.is_local)

        async for event in self._do_stream(sanitized_request):
            yield event
