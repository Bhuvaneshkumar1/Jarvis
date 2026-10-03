"""
Unit Tests for CandidateSelector (Batch 24).
"""

import pytest
from jarvis.llm.contracts import LLMRequest, ChatMessage, RoutingProfile, DataClassification
from jarvis.core.enums import MessageRole
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.routing.candidate_selector import CandidateSelector


@pytest.mark.asyncio
async def test_candidate_selector_privacy_first_ranking(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()
    local_p = LocalLLMProvider(enabled=True, models_dir=str(tmp_path), runtime=MockLocalRuntime())
    cloud_p = OpenRouterProvider(api_key="sk-test")

    await local_p.initialize()
    await cloud_p.initialize()

    registry.register_provider(local_p)
    registry.register_provider(cloud_p)

    selector = CandidateSelector(registry=registry)

    req = LLMRequest(
        model_id="default",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
        data_classification=DataClassification.PUBLIC,
    )

    chain, evaluations = await selector.select_candidates(req, profile=RoutingProfile.PRIVACY_FIRST)

    assert len(chain) > 0
    # First candidate in PRIVACY_FIRST should be local provider
    first_provider = chain[0][0]
    assert first_provider.is_local is True


@pytest.mark.asyncio
async def test_candidate_selector_filters_confidential_from_cloud(tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    registry = LLMProviderRegistry()
    local_p = LocalLLMProvider(enabled=True, models_dir=str(tmp_path), runtime=MockLocalRuntime())
    cloud_p = OpenRouterProvider(api_key="sk-test")

    await local_p.initialize()
    await cloud_p.initialize()

    registry.register_provider(local_p)
    registry.register_provider(cloud_p)

    selector = CandidateSelector(registry=registry)

    req = LLMRequest(
        model_id="default",
        messages=[ChatMessage(role=MessageRole.USER, content="Secret")],
        data_classification=DataClassification.CONFIDENTIAL,
    )

    chain, evaluations = await selector.select_candidates(req, profile=RoutingProfile.BALANCED)

    # Cloud provider must be completely excluded from chain for CONFIDENTIAL data
    for provider, model_id in chain:
        assert provider.is_local is True
