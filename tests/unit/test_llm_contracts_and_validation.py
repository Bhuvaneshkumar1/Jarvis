"""
Unit Tests for LLM Contracts, Serialization, and Validation Rules (Batch 20).
"""

import pytest
from pydantic import ValidationError

from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMRequestContract,
    LLMResponseContract,
    LLMUsage,
    LLMToolCall,
)


def test_llm_request_valid_construction():
    msg = ChatMessage(role=MessageRole.USER, content="Explain quantum computing.")
    req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        temperature=0.5,
        max_tokens=1000,
        metadata={"user_tier": "pro"},
    )
    assert req.request_id.startswith("llmreq-")
    assert req.model_id == "test-model-v1"
    assert req.model == "test-model-v1"  # Backward compatibility property
    assert req.temperature == 0.5


def test_llm_request_invalid_temperature_bounds():
    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    with pytest.raises(ValidationError):
        LLMRequest(model_id="model-1", messages=[msg], temperature=-0.1)

    with pytest.raises(ValidationError):
        LLMRequest(model_id="model-1", messages=[msg], temperature=2.5)


def test_llm_request_empty_id_rejection():
    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    with pytest.raises(ValidationError):
        LLMRequest(request_id="   ", model_id="model-1", messages=[msg])

    with pytest.raises(ValidationError):
        LLMRequest(model_id="  ", messages=[msg])


def test_llm_request_secret_metadata_anti_leakage():
    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    test_key = "sk-" + "a" * 25
    with pytest.raises(ValidationError, match="secret patterns"):
        LLMRequest(
            model_id="model-1",
            messages=[msg],
            metadata={"secret_key": test_key},
        )


def test_llm_response_immutability_and_aliases():
    res = LLMResponse(
        request_id="llmreq-test1",
        provider_id="test_deterministic",
        model_id="test-model-v1",
        generated_content="Test response",
        latency=0.15,
    )
    assert res.provider == "test_deterministic"
    assert res.model == "test-model-v1"
    assert res.content == "Test response"

    with pytest.raises(ValidationError):
        res.generated_content = "Mutated content"


def test_llm_usage_total_computation():
    usage = LLMUsage(input_tokens=150, output_tokens=50)
    assert usage.total_tokens == 200


def test_llm_tool_call_validation():
    tc = LLMToolCall(tool_call_id="call-1", tool_name="search_files", arguments={"query": "test"})
    assert tc.tool_call_id == "call-1"
    assert tc.tool_name == "search_files"

    with pytest.raises(ValidationError):
        LLMToolCall(tool_call_id="  ", tool_name="test")


def test_backward_compatibility_aliases():
    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequestContract(model="test-model-v1", messages=[msg])
    assert isinstance(req, LLMRequest)

    res = LLMResponseContract(request_id="llmreq-1", provider="test", model="test-model-v1", content="Hi")
    assert isinstance(res, LLMResponse)
