"""
Unit Tests for LLMProviderFactory and Configuration Validation (Batch 20).
"""

import pytest
from unittest.mock import MagicMock

from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.factory import (
    LLMProviderFactory,
    LLMSubsystemConfig,
    LLMProviderConfig,
)
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import LLMConfigurationError


def test_factory_disabled_provider_skipping():
    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry)

    factory.register_provider_class("test_deterministic", TestDeterministicLLMProvider)

    config = LLMSubsystemConfig(
        providers={
            "test_deterministic": LLMProviderConfig(enabled=False),
            "nvidia": LLMProviderConfig(enabled=False, api_key_name="NVIDIA_API_KEY"),
        }
    )

    factory.initialize_from_config(config)

    # Disabled providers are not registered
    assert registry.has_provider("test_deterministic") is False
    assert len(registry.list_providers()) == 0


def test_factory_api_key_resolution_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test-secret-key-1234567890")

    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry)

    config = LLMProviderConfig(enabled=True, api_key_name="TEST_LLM_KEY")
    resolved = factory.resolve_api_key(config)

    assert resolved == "sk-test-secret-key-1234567890"


def test_factory_api_key_resolution_from_secrets_manager():
    mock_secrets_mgr = MagicMock()
    mock_val = MagicMock()
    mock_val.get_unredacted_value.return_value = "sk-sec-mgr-key-9999"
    mock_res = MagicMock(allowed=True, secret_value=mock_val)
    mock_secrets_mgr.get_secret.return_value = mock_res

    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry, secrets_manager=mock_secrets_mgr)

    config = LLMProviderConfig(enabled=True, api_key_name="MY_SECRET")
    resolved = factory.resolve_api_key(config)

    assert resolved == "sk-sec-mgr-key-9999"


def test_factory_enabled_provider_instantiation():
    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry)

    factory.register_provider_class("test_deterministic", TestDeterministicLLMProvider)

    config = LLMSubsystemConfig(
        providers={
            "test_deterministic": LLMProviderConfig(enabled=True),
        }
    )

    factory.initialize_from_config(config)

    assert registry.has_provider("test_deterministic") is True
    provider = registry.get_provider("test_deterministic")
    assert isinstance(provider, TestDeterministicLLMProvider)


def test_factory_duplicate_class_registration_rejection():
    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry)

    factory.register_provider_class("p1", TestDeterministicLLMProvider)

    with pytest.raises(LLMConfigurationError, match="Duplicate factory registration"):
        factory.register_provider_class("p1", TestDeterministicLLMProvider)
