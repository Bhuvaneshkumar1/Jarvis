"""
Unit Tests for Model Capability Validation and LLM Generation (Batch 20).
"""

import pytest
from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest, LLMProviderState
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import (
    UnsupportedCapabilityError,
    ContextLengthExceededError,
    ProviderUnavailableError,
)


@pytest.mark.asyncio
async def test_unsupported_streaming_capability_rejection():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(model_id="test-model-basic", messages=[msg], stream=True)

    with pytest.raises(UnsupportedCapabilityError, match="does not support streaming"):
        async for _ in provider.stream(req):
            pass


@pytest.mark.asyncio
async def test_unsupported_structured_output_capability_rejection():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(
        model_id="test-model-basic",
        messages=[msg],
        response_format={"type": "json_object"},
    )

    with pytest.raises(UnsupportedCapabilityError, match="does not support structured JSON"):
        await provider.generate(req)


@pytest.mark.asyncio
async def test_unsupported_tool_calling_capability_rejection():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(
        model_id="test-model-basic",
        messages=[msg],
        tools=[{"name": "test_tool"}],
    )

    with pytest.raises(UnsupportedCapabilityError, match="does not support tool/function calling"):
        await provider.generate(req)


@pytest.mark.asyncio
async def test_context_length_exceeded_rejection():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(
        model_id="test-model-basic",  # max_output_tokens is 1024
        messages=[msg],
        max_tokens=2048,
    )

    with pytest.raises(ContextLengthExceededError, match="exceeds model output cap"):
        await provider.generate(req)


@pytest.mark.asyncio
async def test_provider_unready_state_rejection():
    provider = TestDeterministicLLMProvider()
    provider.state = LLMProviderState.UNAVAILABLE

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(model_id="test-model-v1", messages=[msg])

    with pytest.raises(ProviderUnavailableError, match="is not in READY state"):
        await provider.generate(req)


@pytest.mark.asyncio
async def test_successful_text_generation():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello world")
    req = LLMRequest(model_id="test-model-v1", messages=[msg])

    response = await provider.generate(req)

    assert response.request_id == req.request_id
    assert response.provider_id == "test_deterministic"
    assert response.model_id == "test-model-v1"
    assert response.generated_content is not None
    assert response.usage is not None
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0
