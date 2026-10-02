"""
llama.cpp local runtime adapter and MockLocalRuntime for JARVIS (Batch 23).

Provides real GGUF model execution using llama-cpp-python when available,
and a deterministic MockLocalRuntime for offline unit testing.
"""

import time
import asyncio
from typing import Dict, Any, Optional, AsyncIterator
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
    LLMStreamEvent,
    StreamEventType,
)
from jarvis.llm.exceptions import (
    LLMProviderInitializationError,
    LLMInferenceError,
    LLMTimeoutError,
)
from jarvis.llm.local_runtime.base import AbstractLocalRuntime
from jarvis.llm.local_runtime.resource_manager import LocalResourceManager
import logging

logger = logging.getLogger(__name__)

# Try importing llama_cpp
try:
    import llama_cpp

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    llama_cpp = None
    LLAMA_CPP_AVAILABLE = False


class LlamaCppRuntime(AbstractLocalRuntime):
    """Real GGUF model runtime adapter backed by llama-cpp-python."""

    def __init__(self):
        self.llm = None
        self._loaded_path: Optional[str] = None
        self._context_window: int = 2048
        self._threads: int = 4
        self._gpu_layers: int = 0

    async def load_model(
        self,
        model_path: str,
        context_window: int = 2048,
        threads: int = 4,
        gpu_layers: int = 0,
    ) -> bool:
        if not LLAMA_CPP_AVAILABLE:
            raise LLMProviderInitializationError("llama-cpp-python is not installed. Install it via `pip install llama-cpp-python` to use local GGUF models.")

        if self.is_loaded():
            if self._loaded_path == model_path:
                logger.info(f"Model already loaded: {model_path}")
                return True
            await self.unload_model()

        def _do_load():
            return llama_cpp.Llama(
                model_path=model_path,
                n_ctx=context_window,
                n_threads=threads if threads > 0 else None,
                n_gpu_layers=gpu_layers,
                verbose=False,
            )

        try:
            loop = asyncio.get_running_loop()
            self.llm = await loop.run_in_executor(None, _do_load)
            self._loaded_path = model_path
            self._context_window = context_window
            self._threads = threads
            self._gpu_layers = gpu_layers
            logger.info(f"Successfully loaded GGUF model: {model_path} (n_ctx={context_window}, n_threads={threads}, n_gpu_layers={gpu_layers})")
            return True
        except Exception as e:
            self.llm = None
            self._loaded_path = None
            logger.error(f"Failed to load GGUF model at {model_path}: {e}")
            raise LLMProviderInitializationError(f"Failed to load local GGUF model: {e}") from e

    async def unload_model(self) -> None:
        if self.llm is not None:

            def _do_unload():
                del self.llm

            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _do_unload)
            except Exception as e:
                logger.warning(f"Error during model unload: {e}")
            finally:
                self.llm = None
                self._loaded_path = None
                logger.info("Local GGUF model unloaded.")

    def is_loaded(self) -> bool:
        return self.llm is not None

    def get_memory_usage_mb(self) -> float:
        if not self.is_loaded():
            return 0.0
        return LocalResourceManager.get_process_memory_mb()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.is_loaded():
            raise LLMInferenceError("No local model loaded in memory for inference.")

        start_time = time.time()

        # Format messages for llama_cpp chat completion
        formatted_messages = []
        if request.system_instructions:
            formatted_messages.append({"role": "system", "content": request.system_instructions})
        for msg in request.messages:
            formatted_messages.append({"role": msg.role.value, "content": msg.content})

        kwargs: Dict[str, Any] = {
            "messages": formatted_messages,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.stop_sequences:
            kwargs["stop"] = request.stop_sequences

        def _do_inference():
            return self.llm.create_chat_completion(**kwargs)

        try:
            loop = asyncio.get_running_loop()
            res = await asyncio.wait_for(loop.run_in_executor(None, _do_inference), timeout=request.timeout)
        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"Local LLM inference timed out after {request.timeout}s.")
        except Exception as e:
            raise LLMInferenceError(f"Local LLM execution error: {e}") from e

        duration = time.time() - start_time
        choices = res.get("choices", [])
        content = choices[0]["message"]["content"] if choices else ""
        finish_reason = choices[0].get("finish_reason", "stop") if choices else "stop"

        raw_usage = res.get("usage", {})
        usage = LLMUsage(
            input_tokens=raw_usage.get("prompt_tokens", 0),
            output_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )

        return LLMResponse(
            request_id=request.request_id,
            provider="local",
            model=request.model_id,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            latency=duration,
            metadata={
                "runtime": "llama.cpp",
                "loaded_path": self._loaded_path,
                "context_window": self._context_window,
                "gpu_layers": self._gpu_layers,
            },
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if not self.is_loaded():
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message="No local model loaded in memory for streaming inference.",
            )
            return

        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_STARTED,
        )

        formatted_messages = []
        if request.system_instructions:
            formatted_messages.append({"role": "system", "content": request.system_instructions})
        for msg in request.messages:
            formatted_messages.append({"role": msg.role.value, "content": msg.content})

        kwargs: Dict[str, Any] = {
            "messages": formatted_messages,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.stop_sequences:
            kwargs["stop"] = request.stop_sequences

        def _get_stream_chunks():
            return self.llm.create_chat_completion(**kwargs)

        try:
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(None, _get_stream_chunks)
            for chunk in chunks:
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text_chunk = delta.get("content", "")
                    finish_reason = choices[0].get("finish_reason")
                    if text_chunk:
                        yield LLMStreamEvent(
                            request_id=request.request_id,
                            event_type=StreamEventType.TEXT_DELTA,
                            text_delta=text_chunk,
                        )
                    if finish_reason:
                        yield LLMStreamEvent(
                            request_id=request.request_id,
                            event_type=StreamEventType.STREAM_COMPLETED,
                            finish_reason=finish_reason,
                        )
                        return
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_COMPLETED,
                finish_reason="stop",
            )
        except Exception as e:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message=str(e),
            )


class MockLocalRuntime(AbstractLocalRuntime):
    """Deterministic mock local runtime for offline unit and integration testing."""

    def __init__(self, default_response: str = "JARVIS Local LLM Mock Response"):
        self._loaded: bool = False
        self._loaded_path: Optional[str] = None
        self.default_response = default_response
        self.simulated_memory_mb: float = 512.0

    async def load_model(
        self,
        model_path: str,
        context_window: int = 2048,
        threads: int = 4,
        gpu_layers: int = 0,
    ) -> bool:
        if "fail_load" in model_path:
            raise LLMProviderInitializationError("Simulated model load failure for testing.")
        self._loaded = True
        self._loaded_path = model_path
        return True

    async def unload_model(self) -> None:
        self._loaded = False
        self._loaded_path = None

    def is_loaded(self) -> bool:
        return self._loaded

    def get_memory_usage_mb(self) -> float:
        return self.simulated_memory_mb if self._loaded else 0.0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._loaded:
            raise LLMInferenceError("No local model loaded in memory for inference.")

        start_time = time.time()
        await asyncio.sleep(0.01)  # Simulate brief inference latency

        if self.default_response.strip().startswith("{") or self.default_response.strip().startswith("["):
            content = self.default_response
        else:
            content = f"{self.default_response} [Prompt tokens: {len(request.messages[0].content)}]"
        in_tokens = max(10, len(request.messages[0].content) // 4)
        out_tokens = max(5, len(content) // 4)

        return LLMResponse(
            request_id=request.request_id,
            provider="local",
            model=request.model_id,
            content=content,
            finish_reason="stop",
            usage=LLMUsage(
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=in_tokens + out_tokens,
            ),
            latency=time.time() - start_time,
            metadata={"runtime": "MockLocalRuntime", "loaded_path": self._loaded_path},
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if not self._loaded:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message="No local model loaded in memory for streaming inference.",
            )
            return

        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_STARTED,
        )

        words = self.default_response.split()
        for word in words:
            await asyncio.sleep(0.005)
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.TEXT_DELTA,
                text_delta=f"{word} ",
            )

        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_COMPLETED,
            finish_reason="stop",
            usage=LLMUsage(input_tokens=15, output_tokens=len(words), total_tokens=15 + len(words)),
        )
