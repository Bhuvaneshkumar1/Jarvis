"""
Unit Tests for RoutingPolicyEngine (Batch 24).
"""

from jarvis.llm.contracts import LLMRequest, ChatMessage, DataClassification
from jarvis.core.enums import MessageRole
from jarvis.llm.routing.routing_policy import RoutingPolicyEngine
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime


def test_privacy_allows_public_on_cloud():
    policy = RoutingPolicyEngine()
    cloud_provider = OpenRouterProvider(api_key="sk-or-dummy")
    req = LLMRequest(
        model_id="gpt-4o",
        messages=[ChatMessage(role=MessageRole.USER, content="Public content")],
        data_classification=DataClassification.PUBLIC,
    )

    allowed, reason = policy.is_provider_allowed_by_privacy(req, cloud_provider)
    assert allowed is True


def test_privacy_blocks_confidential_on_cloud():
    policy = RoutingPolicyEngine()
    cloud_provider = OpenRouterProvider(api_key="sk-or-dummy")
    req = LLMRequest(
        model_id="gpt-4o",
        messages=[ChatMessage(role=MessageRole.USER, content="Secret content")],
        data_classification=DataClassification.CONFIDENTIAL,
    )

    allowed, reason = policy.is_provider_allowed_by_privacy(req, cloud_provider)
    assert allowed is False
    assert "data classification is CONFIDENTIAL" in reason


def test_privacy_allows_confidential_on_local():
    policy = RoutingPolicyEngine()
    local_provider = LocalLLMProvider(enabled=True, runtime=MockLocalRuntime())
    req = LLMRequest(
        model_id="local-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Secret content")],
        data_classification=DataClassification.CONFIDENTIAL,
    )

    allowed, reason = policy.is_provider_allowed_by_privacy(req, local_provider)
    assert allowed is True


def test_local_only_flag_blocks_cloud():
    policy = RoutingPolicyEngine()
    cloud_provider = OpenRouterProvider(api_key="sk-or-dummy")
    req = LLMRequest(
        model_id="gpt-4o",
        messages=[ChatMessage(role=MessageRole.USER, content="Local only")],
        local_only=True,
    )

    allowed, reason = policy.is_provider_allowed_by_privacy(req, cloud_provider)
    assert allowed is False
    assert "request requires local_only processing" in reason
