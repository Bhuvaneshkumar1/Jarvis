"""
Unit Tests for Provider-Neutral Streaming Foundation (Batch 20).
"""

import pytest
from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest, StreamEventType
from jarvis.llm.test_provider import TestDeterministicLLMProvider


@pytest.mark.asyncio
async def test_deterministic_streaming_event_sequence():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Stream message")
    req = LLMRequest(model_id="test-model-v1", messages=[msg], stream=True)

    events = []
    async for event in provider.stream(req):
        events.append(event)

    assert len(events) >= 4
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    assert events[-1].event_type == StreamEventType.STREAM_COMPLETED
    assert events[-1].finish_reason == "stop"

    text_deltas = [e.text_delta for e in events if e.event_type == StreamEventType.TEXT_DELTA]
    full_text = "".join(filter(None, text_deltas))
    assert "Deterministic streaming response" in full_text


@pytest.mark.asyncio
async def test_streaming_simulated_error_event():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="trigger_stream_error")
    req = LLMRequest(model_id="test-model-v1", messages=[msg], stream=True)

    events = []
    async for event in provider.stream(req):
        events.append(event)

    assert len(events) == 2
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    assert events[1].event_type == StreamEventType.STREAM_FAILED
    assert "simulated stream interruption" in events[1].error_message.lower()
