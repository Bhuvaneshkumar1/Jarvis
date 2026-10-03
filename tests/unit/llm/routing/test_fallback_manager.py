"""
Unit Tests for FallbackManager (Batch 24).
"""

from jarvis.llm.contracts import LLMRequest, ChatMessage, DataClassification
from jarvis.core.enums import MessageRole
from jarvis.llm.routing.fallback_manager import FallbackManager
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.exceptions import (
    ProviderTimeoutError,
    InvalidLLMRequestError,
)


def test_fallback_retryable_timeout():
    mgr = FallbackManager(max_attempts=3, allow_fallback=True)
    req = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
    )
    next_p = OpenRouterProvider(api_key="sk-test")
    err = ProviderTimeoutError("Request timed out")

    can_fb, reason = mgr.can_fallback(req, current_attempt=1, error=err, next_provider=next_p)
    assert can_fb is True


def test_fallback_blocks_non_retryable_error():
    mgr = FallbackManager(max_attempts=3, allow_fallback=True)
    req = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
    )
    next_p = OpenRouterProvider(api_key="sk-test")
    err = InvalidLLMRequestError("Invalid json")

    can_fb, reason = mgr.can_fallback(req, current_attempt=1, error=err, next_provider=next_p)
    assert can_fb is False
    assert "non-retryable" in reason


def test_fallback_blocks_attempts_exceeded():
    mgr = FallbackManager(max_attempts=2, allow_fallback=True)
    req = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
    )
    next_p = OpenRouterProvider(api_key="sk-test")
    err = ProviderTimeoutError("Timeout")

    can_fb, reason = mgr.can_fallback(req, current_attempt=2, error=err, next_provider=next_p)
    assert can_fb is False
    assert "Maximum provider attempts" in reason


def test_fallback_blocks_external_for_confidential_data():
    mgr = FallbackManager(max_attempts=3, allow_fallback=True)
    req = LLMRequest(
        model_id="test",
        messages=[ChatMessage(role=MessageRole.USER, content="Secret")],
        data_classification=DataClassification.CONFIDENTIAL,
    )
    next_p = OpenRouterProvider(api_key="sk-test")  # External
    err = ProviderTimeoutError("Timeout")

    can_fb, reason = mgr.can_fallback(req, current_attempt=1, error=err, next_provider=next_p)
    assert can_fb is False
    assert "blocked for local_only / CONFIDENTIAL" in reason
