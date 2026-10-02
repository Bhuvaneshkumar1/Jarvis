"""
Unit Tests for LLMProviderRegistry (Batch 20).
"""

import pytest
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import ProviderNotFoundError, LLMConfigurationError
from jarvis.llm.contracts import LLMProviderState


@pytest.mark.asyncio
async def test_provider_registration_and_lookup():
    registry = LLMProviderRegistry()
    provider = TestDeterministicLLMProvider(provider_id="test_prov_1")

    registry.register_provider(provider)

    assert registry.has_provider("test_prov_1") is True
    retrieved = registry.get_provider("test_prov_1")
    assert retrieved is provider
    assert len(registry.list_providers()) == 1


def test_duplicate_provider_registration_rejection():
    registry = LLMProviderRegistry()
    provider1 = TestDeterministicLLMProvider(provider_id="test_prov_1")
    provider2 = TestDeterministicLLMProvider(provider_id="test_prov_1")

    registry.register_provider(provider1)

    with pytest.raises(LLMConfigurationError, match="Duplicate LLM provider registration"):
        registry.register_provider(provider2)


def test_provider_not_found_raises_exception():
    registry = LLMProviderRegistry()
    with pytest.raises(ProviderNotFoundError, match="is not registered"):
        registry.get_provider("non_existent_provider")


@pytest.mark.asyncio
async def test_unregister_provider():
    registry = LLMProviderRegistry()
    provider = TestDeterministicLLMProvider(provider_id="test_prov_1")

    registry.register_provider(provider)
    assert registry.has_provider("test_prov_1") is True

    unregistered = registry.unregister_provider("test_prov_1")
    assert unregistered is provider
    assert registry.has_provider("test_prov_1") is False


@pytest.mark.asyncio
async def test_close_all_providers_on_shutdown():
    registry = LLMProviderRegistry()
    p1 = TestDeterministicLLMProvider(provider_id="p1")
    p2 = TestDeterministicLLMProvider(provider_id="p2")

    registry.register_provider(p1)
    registry.register_provider(p2)

    await registry.close_all()

    assert p1.state == LLMProviderState.CLOSED
    assert p2.state == LLMProviderState.CLOSED
    assert len(registry.list_providers()) == 0
