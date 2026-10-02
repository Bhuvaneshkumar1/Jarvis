"""
Deterministic Test LLM Provider Fixture for Subsystem Verification (Batch 20).
THIS PROVIDER IS A TEST FIXTURE AND MUST NOT BE USED AS A PRODUCTION PROVIDER.
"""

import time
import json
import asyncio
from typing import List, Optional, AsyncIterator, Dict, Any

from jarvis.core.enums import HealthState
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StreamEventType,
    LLMUsage,
    LLMToolCall,
    ModelCapability,
    LLMProviderState,
)
from jarvis.llm.exceptions import (
    ProviderResponseError,
    ContentFilteredError,
)


class TestDeterministicLLMProvider(AbstractLLMProvider):
    """
    Deterministic LLM Provider Fixture for unit, integration, and streaming testing.
    Exposes reproducible generation, streaming, tool calling, and structured output capabilities.
    """

    __test__ = False

    TEST_MODELS = {
        "test-model-v1": ModelCapability(
            model_id="test-model-v1",
            provider_id="test_deterministic",
            supports_text_generation=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_vision=False,
            supports_reasoning=False,
            supports_embeddings=False,
            context_window=8192,
            max_output_tokens=4096,
        ),
        "test-model-basic": ModelCapability(
            model_id="test-model-basic",
            provider_id="test_deterministic",
            supports_text_generation=True,
            supports_streaming=False,
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_vision=False,
            supports_reasoning=False,
            context_window=2048,
            max_output_tokens=1024,
        ),
    }

    def __init__(
        self,
        provider_id: str = "test_deterministic",
        is_local: bool = True,
        config: Optional[Any] = None,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(provider_id=provider_id, is_local=is_local)
        self.config = config
        self.api_key = api_key
        self.state = LLMProviderState.READY

    async def initialize(self) -> None:
        self.state = LLMProviderState.READY

    async def close(self) -> None:
        self.state = LLMProviderState.CLOSED

    async def health_check(self) -> HealthState:
        if self.state == LLMProviderState.READY:
            return HealthState.HEALTHY
        return HealthState.UNHEALTHY

    async def list_models(self) -> List[ModelCapability]:
        return list(self.TEST_MODELS.values())

    async def get_capabilities(self, model_id: str) -> ModelCapability:
        cap = self.TEST_MODELS.get(model_id)
        if not cap:
            # Fallback to test-model-v1 capability for custom test model names
            return ModelCapability(
                model_id=model_id,
                provider_id=self.provider_id,
                supports_text_generation=True,
                supports_streaming=True,
                supports_structured_output=True,
                supports_tool_calling=True,
                context_window=8192,
                max_output_tokens=4096,
            )
        return cap

    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()

        # Simulate simulated prompt trigger behaviors
        last_msg = request.messages[-1].content if request.messages else ""

        if "trigger_content_filter" in last_msg:
            raise ContentFilteredError(
                "Request was blocked by simulated content filter safety rule.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        if "trigger_provider_response_error" in last_msg:
            raise ProviderResponseError(
                "Simulated unparseable LLM provider response payload.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        # Handle tool calling requested by prompt or request tools
        tool_calls: List[LLMToolCall] = []
        if request.tools and "trigger_tool_call" in last_msg:
            tool_calls.append(
                LLMToolCall(
                    tool_call_id="call-test-123",
                    tool_name=request.tools[0].get("name", "test_tool"),
                    arguments={"arg1": "test_value"},
                )
            )

        # Handle structured output
        structured_out: Optional[Dict[str, Any]] = None
        generated_content = f"Deterministic response for request '{request.request_id}'."

        if request.response_format:
            structured_out = {
                "status": "success",
                "summary": "Deterministic structured summary",
                "request_id": request.request_id,
            }
            generated_content = json.dumps(structured_out)

        latency = round(time.time() - start_time, 4)
        input_toks = sum(len(m.content.split()) for m in request.messages) + 10
        output_toks = len(generated_content.split()) + 5

        return LLMResponse(
            request_id=request.request_id,
            provider=self.provider_id,
            model=request.model_id,
            content=generated_content,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=LLMUsage(
                input_tokens=input_toks,
                output_tokens=output_toks,
                total_tokens=input_toks + output_toks,
            ),
            latency=latency,
            structured_output=structured_out,
            tool_calls=tool_calls,
            provider_request_id=f"prov-req-{request.request_id}",
        )

    async def _do_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        # Stream start event
        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_STARTED,
        )

        last_msg = request.messages[-1].content if request.messages else ""
        if "trigger_stream_error" in last_msg:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message="Simulated stream interruption error.",
            )
            return

        chunks = ["Deterministic ", "streaming ", "response ", "completed."]
        for chunk in chunks:
            await asyncio.sleep(0.01)
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.TEXT_DELTA,
                text_delta=chunk,
            )

        # Usage update event
        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.USAGE_UPDATE,
            usage=LLMUsage(input_tokens=20, output_tokens=10, total_tokens=30),
        )

        # Stream completed event
        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_COMPLETED,
            finish_reason="stop",
        )
