"""
Local LLM Provider Implementation for JARVIS (Batch 23).

Enables offline, privacy-preserving LLM execution on Windows desktop systems using llama-cpp-python
and GGUF format models, with strict RAM monitoring, path safety, and graceful degradation.
"""

import os
import json
import logging
import asyncio
from typing import List, Optional, Any, AsyncIterator

from jarvis.core.enums import HealthState
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StreamEventType,
    ModelCapability,
    LLMProviderState,
)
from jarvis.llm.exceptions import (
    LLMError,
    ProviderUnavailableError,
    InvalidLLMRequestError,
    LLMProviderInitializationError,
    LLMInferenceError,
)
from jarvis.llm.local_runtime.base import AbstractLocalRuntime
from jarvis.llm.local_runtime.model_manager import LocalModelManager
from jarvis.llm.local_runtime.resource_manager import LocalResourceManager
from jarvis.llm.local_runtime.llama_cpp_runtime import (
    LlamaCppRuntime,
    MockLocalRuntime,
    LLAMA_CPP_AVAILABLE,
)

logger = logging.getLogger("jarvis.llm.providers.local")


class LocalLLMProvider(AbstractLLMProvider):
    """
    Local LLM Provider Integration for GGUF models.
    Supports CPU-only inference, optional GPU offloading, resource-aware loading, and path safety.
    """

    DEFAULT_MODEL_ID = "local-default"

    def __init__(
        self,
        provider_id: str = "local",
        models_dir: Optional[str] = None,
        model_path: Optional[str] = None,
        context_length: Optional[int] = None,
        max_tokens: Optional[int] = None,
        threads: Optional[int] = None,
        gpu_layers: Optional[int] = None,
        max_memory_mb: Optional[float] = None,
        enabled: Optional[bool] = None,
        runtime: Optional[AbstractLocalRuntime] = None,
        config: Optional[Any] = None,
    ) -> None:
        super().__init__(provider_id=provider_id, is_local=True)

        self.enabled = enabled if enabled is not None else os.getenv("LOCAL_LLM_ENABLED", "false").lower() in ("true", "1", "yes")
        self.models_dir: str = models_dir or os.getenv("LOCAL_LLM_MODELS_DIR") or "data/models"
        self.configured_model_path = model_path or os.getenv("LOCAL_LLM_MODEL_PATH")
        self.context_length = context_length or int(os.getenv("LOCAL_LLM_CONTEXT_LENGTH", "2048"))
        self.max_tokens = max_tokens or int(os.getenv("LOCAL_LLM_MAX_TOKENS", "512"))
        self.threads = threads or int(os.getenv("LOCAL_LLM_THREADS", "4"))
        self.gpu_layers = gpu_layers if gpu_layers is not None else int(os.getenv("LOCAL_LLM_GPU_LAYERS", "0"))
        self.max_memory_mb = max_memory_mb or float(os.getenv("LOCAL_LLM_MAX_MEMORY_MB", "4096"))
        self.config = config

        self.model_manager = LocalModelManager(models_dir=self.models_dir)
        self.resource_manager = LocalResourceManager(max_memory_mb=self.max_memory_mb)

        # Inject custom runtime (e.g. MockLocalRuntime) or use real LlamaCppRuntime
        if runtime is not None:
            self.runtime = runtime
        else:
            self.runtime = LlamaCppRuntime()

        self._current_model_path: Optional[str] = None
        self._load_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initializes provider state and attempts default model load if enabled."""
        if not self.enabled:
            self.state = LLMProviderState.UNAVAILABLE
            logger.info("Local LLM Provider is disabled via configuration (LOCAL_LLM_ENABLED=false).")
            return

        self.state = LLMProviderState.INITIALIZING

        # Discover available local models
        discovered = self.model_manager.discover_models()
        logger.info(f"Local model discovery found {len(discovered)} GGUF models in {self.models_dir}.")

        target_path_str = self.configured_model_path
        if not target_path_str and discovered:
            target_path_str = str(discovered[0].file_path)

        if not target_path_str:
            self.state = LLMProviderState.UNAVAILABLE
            logger.warning("No local GGUF model path configured or discovered. Local LLM Provider will remain UNAVAILABLE.")
            return

        # Attempt model load
        try:
            await self.load_model(target_path_str)
            self.state = LLMProviderState.READY
        except Exception as e:
            self.state = LLMProviderState.UNAVAILABLE
            logger.warning(f"Failed to auto-load local GGUF model '{target_path_str}': {e}")

    async def load_model(self, model_path_str: str) -> bool:
        """Loads a specific GGUF model after path validation and RAM resource checks."""
        async with self._load_lock:
            # Validate file existence, readability, and path traversal safety
            valid_path = self.model_manager.validate_model_path(model_path_str)
            file_size = valid_path.stat().st_size

            # Check RAM resource availability
            can_load, reason = self.resource_manager.can_load_model(file_size, self.context_length)
            if not can_load:
                logger.error(f"Cannot load local model '{valid_path}': {reason}")
                raise LLMProviderInitializationError(f"Resource check failed for local model load: {reason}")

            # Execute load in runtime
            success = await self.runtime.load_model(
                model_path=str(valid_path),
                context_window=self.context_length,
                threads=self.threads,
                gpu_layers=self.gpu_layers,
            )

            if success:
                self._current_model_path = str(valid_path)
                self.state = LLMProviderState.READY
                logger.info(f"Local LLM Provider loaded model: {valid_path}")

            return success

    async def unload_model(self) -> None:
        """Unloads current model from RAM."""
        async with self._load_lock:
            await self.runtime.unload_model()
            self._current_model_path = None
            if self.enabled:
                self.state = LLMProviderState.UNAVAILABLE
            logger.info("Local LLM model unloaded.")

    async def close(self) -> None:
        """Gracefully releases model resources on shutdown."""
        self.state = LLMProviderState.CLOSING
        await self.unload_model()
        self.state = LLMProviderState.CLOSED
        logger.info("Local LLM Provider closed successfully.")

    async def health_check(self) -> HealthState:
        """Performs non-disruptive health inspection."""
        if not self.enabled:
            return HealthState.UNHEALTHY

        if self.runtime.is_loaded():
            return HealthState.HEALTHY

        # Check if runtime dependency and models exist without loading
        if LLAMA_CPP_AVAILABLE or isinstance(self.runtime, MockLocalRuntime):
            discovered = self.model_manager.discover_models()
            if discovered or self.configured_model_path:
                return HealthState.DEGRADED

        return HealthState.UNHEALTHY

    async def list_models(self) -> List[ModelCapability]:
        """Lists capabilities for all discovered GGUF models."""
        models: List[ModelCapability] = []
        discovered = self.model_manager.discover_models()

        if not discovered and self._current_model_path:
            meta = self.model_manager.get_model_info(self._current_model_path)
            if meta:
                discovered.append(meta)

        for m in discovered:
            models.append(
                ModelCapability(
                    model_id=m.model_id,
                    provider_id=self.provider_id,
                    supports_text_generation=True,
                    supports_streaming=True,
                    supports_structured_output=True,
                    supports_tool_calling=False,
                    context_window=self.context_length,
                    max_output_tokens=self.max_tokens,
                )
            )

        if not models:
            # Fallback capability entry
            models.append(
                ModelCapability(
                    model_id=self.DEFAULT_MODEL_ID,
                    provider_id=self.provider_id,
                    supports_text_generation=True,
                    supports_streaming=True,
                    supports_structured_output=True,
                    supports_tool_calling=False,
                    context_window=self.context_length,
                    max_output_tokens=self.max_tokens,
                )
            )

        return models

    async def get_capabilities(self, model_id: str) -> ModelCapability:
        """Retrieves capabilities for a model ID."""
        catalog = await self.list_models()
        for cap in catalog:
            if cap.model_id == model_id or model_id in (
                self.DEFAULT_MODEL_ID,
                "local",
                "default",
            ):
                return cap

        return ModelCapability(
            model_id=model_id,
            provider_id=self.provider_id,
            supports_text_generation=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_tool_calling=False,
            context_window=self.context_length,
            max_output_tokens=self.max_tokens,
        )

    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        """Executes local synchronous inference."""
        if not self.runtime.is_loaded():
            raise ProviderUnavailableError(
                "Local LLM runtime has no model loaded in memory.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        try:
            response = await self.runtime.generate(request)

            # JSON Structured Output validation if requested
            if request.response_format and request.response_format.get("type") == "json_object":
                if response.generated_content:
                    try:
                        structured_json = json.loads(response.generated_content)
                        # Re-create response with structured_output populated
                        response = LLMResponse(
                            request_id=response.request_id,
                            provider=self.provider_id,
                            model=response.model_id,
                            content=response.generated_content,
                            finish_reason=response.finish_reason,
                            usage=response.usage,
                            latency=response.latency,
                            structured_output=structured_json,
                            metadata=response.metadata,
                        )
                    except json.JSONDecodeError as err:
                        raise InvalidLLMRequestError(
                            f"Local LLM output failed JSON validation: {err}",
                        ) from err

            return response
        except LLMError:
            raise
        except Exception as e:
            raise LLMInferenceError(
                f"Local LLM provider execution failed: {e}",
            ) from e

    async def _do_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Executes local incremental token streaming inference."""
        if not self.runtime.is_loaded():
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message="Local LLM runtime has no model loaded in memory.",
            )
            return

        try:
            async for event in self.runtime.generate_stream(request):
                yield event
        except Exception as e:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message=f"Local LLM streaming error: {e}",
            )
