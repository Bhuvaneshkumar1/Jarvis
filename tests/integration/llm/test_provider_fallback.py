"""
Integration Tests for LLMRouter Provider Fallback (Batch 24).
Verifies fallback execution when primary candidate fails with a retryable error.
"""

import pytest
from jarvis.llm.contracts import (
    LLMRequest,
    ChatMessage,
    RoutingProfile,
    ModelCapability,
    LLMProviderState,
    LLMStreamEvent,
    StreamEventType,
)
from jarvis.core.enums import MessageRole, HealthState
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.exceptions import ProviderTimeoutError
from jarvis.llm.router import LLMRouter


class FailingTestProvider(AbstractLLMProvider):
    """Failing provider test double simulating a network/timeout failure."""

    def __init__(self, provider_id: str = "failing_primary"):
        super().__init__(provider_id=provider_id, is_local=False)

    async def initialize(self):
        self.state = LLMProviderState.READY

    async def close(self):
        pass

    async def health_check(self):
        return HealthState.HEALTHY

    async def list_models(self):
        return [ModelCapability(model_id="failing-model", provider_id=self.provider_id)]

    async def get_capabilities(self, model_id: str):
        return (await self.list_models())[0]

    async def _do_generate(self, request: LLMRequest):
        raise ProviderTimeoutError(f"Simulated timeout on provider '{self.provider_id}'")

    async def _do_stream(self, request: LLMRequest):
        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_FAILED,
            error_message="Simulated stream timeout",
        )


@pytest.mark.asyncio
async def test_integration_fallback_on_primary_failure(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()

    primary_failing = FailingTestProvider(provider_id="failing_primary")
    secondary_local = LocalLLMProvider(
        enabled=True,
        models_dir=str(tmp_path),
        runtime=MockLocalRuntime(default_response="Secondary Fallback Output"),
    )

    await primary_failing.initialize()
    await secondary_local.initialize()

    registry.register_provider(primary_failing)
    registry.register_provider(secondary_local)

    router = LLMRouter(registry=registry, default_profile=RoutingProfile.BALANCED)
    await router.initialize()

    req = LLMRequest(
        model_id="failing-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Fallback Test Prompt")],
    )

    res = await router.generate(req)

    assert res.content is not None
    assert "Secondary Fallback Output" in res.content
    assert res.provider_id == "local"

    # Explanation metadata checks
    explanation = res.metadata.get("routing_explanation")
    assert explanation is not None
    assert explanation["fallback_occurred"] is True
    assert len(explanation["attempts"]) == 2
    assert explanation["attempts"][0]["status"] == "FAILED"
    assert explanation["attempts"][1]["status"] == "SUCCESS"

    await router.close()
