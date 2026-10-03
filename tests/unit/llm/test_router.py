"""
Unit Tests for LLMRouter Central Entry Point (Batch 24).
"""

import pytest
from jarvis.llm.contracts import (
    LLMRequest,
    ChatMessage,
    DataClassification,
    StreamEventType,
)
from jarvis.core.enums import MessageRole, HealthState
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import ProviderUnavailableError
from jarvis.llm.router import LLMRouter


@pytest.mark.asyncio
async def test_router_initialization_and_health(tmp_path):
    registry = LLMProviderRegistry()
    test_p = TestDeterministicLLMProvider()
    await test_p.initialize()
    registry.register_provider(test_p)

    router = LLMRouter(registry=registry)
    await router.initialize()

    health = await router.health_check()
    assert health == HealthState.HEALTHY

    models = await router.list_models()
    assert len(models) > 0

    await router.close()


@pytest.mark.asyncio
async def test_router_generation_routing(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()
    local_p = LocalLLMProvider(enabled=True, models_dir=str(tmp_path), runtime=MockLocalRuntime(default_response="Local Output"))
    await local_p.initialize()
    registry.register_provider(local_p)

    router = LLMRouter(registry=registry)
    await router.initialize()

    req = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello Router")],
    )

    res = await router.generate(req)
    assert res.content is not None
    assert "Local Output" in res.content
    assert "routing_explanation" in res.metadata

    await router.close()


@pytest.mark.asyncio
async def test_router_blocks_confidential_when_no_local_provider():
    registry = LLMProviderRegistry()
    # Register only a cloud / non-local provider
    test_p = TestDeterministicLLMProvider(provider_id="cloud-test", is_local=False)
    await test_p.initialize()
    registry.register_provider(test_p)

    router = LLMRouter(registry=registry)
    await router.initialize()

    req = LLMRequest(
        model_id="cloud-test",
        messages=[ChatMessage(role=MessageRole.USER, content="Confidential Data")],
        data_classification=DataClassification.CONFIDENTIAL,
    )

    with pytest.raises(ProviderUnavailableError, match="No eligible LLM providers satisfy privacy and capability bounds"):
        await router.generate(req)

    await router.close()


@pytest.mark.asyncio
async def test_router_streaming(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()
    local_p = LocalLLMProvider(enabled=True, models_dir=str(tmp_path), runtime=MockLocalRuntime(default_response="Stream Token Output"))
    await local_p.initialize()
    registry.register_provider(local_p)

    router = LLMRouter(registry=registry)
    await router.initialize()

    req = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Stream request")],
        stream=True,
    )

    events = []
    async for ev in router.stream(req):
        events.append(ev)

    assert len(events) >= 3
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    assert events[-1].event_type == StreamEventType.STREAM_COMPLETED

    await router.close()
