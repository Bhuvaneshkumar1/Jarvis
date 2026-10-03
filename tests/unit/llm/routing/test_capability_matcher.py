"""
Unit Tests for CapabilityMatcher (Batch 24).
"""

from jarvis.llm.contracts import LLMRequest, ChatMessage, ModelCapability
from jarvis.core.enums import MessageRole
from jarvis.llm.routing.capability_matcher import CapabilityMatcher


def test_evaluate_capable_model():
    cap = ModelCapability(
        model_id="capable-model",
        provider_id="test",
        supports_text_generation=True,
        supports_streaming=True,
        supports_structured_output=True,
        supports_tool_calling=True,
        context_window=4096,
    )
    req = LLMRequest(
        model_id="capable-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
        stream=True,
        response_format={"type": "json_object"},
    )

    is_ok, missing = CapabilityMatcher.evaluate_capability(cap, req)
    assert is_ok is True
    assert len(missing) == 0


def test_evaluate_incapable_model():
    cap = ModelCapability(
        model_id="simple-model",
        provider_id="test",
        supports_text_generation=True,
        supports_streaming=False,
        supports_structured_output=False,
        supports_tool_calling=False,
        context_window=200,
    )
    req = LLMRequest(
        model_id="simple-model",
        messages=[ChatMessage(role=MessageRole.USER, content="A" * 1000)],
        stream=True,
        tools=[{"name": "fn"}],
    )

    is_ok, missing = CapabilityMatcher.evaluate_capability(cap, req)
    assert is_ok is False
    assert "streaming_unsupported" in missing
    assert "tool_calling_unsupported" in missing
    assert any("context_length_exceeded" in m for m in missing)
