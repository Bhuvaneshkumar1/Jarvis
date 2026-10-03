"""
Integration Tests for LLMRouter Provider Routing (Batch 24).
Verifies multi-provider registration, task classification, and candidate ordering.
"""

import pytest
from jarvis.llm.contracts import (
    LLMRequest,
    ChatMessage,
    DataClassification,
)
from jarvis.core.enums import MessageRole
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.router import LLMRouter


@pytest.mark.asyncio
async def test_integration_routing_across_registered_providers(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()

    local_p = LocalLLMProvider(enabled=True, models_dir=str(tmp_path), runtime=MockLocalRuntime(default_response="Offline Local Output"))
    cloud_p = TestDeterministicLLMProvider(provider_id="openrouter", is_local=False)

    await local_p.initialize()
    await cloud_p.initialize()

    registry.register_provider(local_p)
    registry.register_provider(cloud_p)

    router = LLMRouter(registry=registry)
    await router.initialize()

    # Public request -> selects best candidate
    req_pub = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Public task")],
        data_classification=DataClassification.PUBLIC,
    )
    res_pub = await router.generate(req_pub)
    assert res_pub.content is not None
    assert "routing_explanation" in res_pub.metadata

    # Confidential request -> strictly routed to local provider
    req_conf = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Confidential task")],
        data_classification=DataClassification.CONFIDENTIAL,
    )
    res_conf = await router.generate(req_conf)
    assert "Offline Local Output" in res_conf.content
    assert res_conf.provider_id == "local"

    await router.close()
