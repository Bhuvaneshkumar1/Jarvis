"""
Unit Tests for Timeouts and Request Cancellation (Batch 20).
"""

import asyncio
import pytest
from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import ProviderTimeoutError


class SlowTestLLMProvider(TestDeterministicLLMProvider):
    """Subclass simulating slow model generation for timeout testing."""

    async def _do_generate(self, request: LLMRequest):
        await asyncio.sleep(2.0)
        return await super()._do_generate(request)


@pytest.mark.asyncio
async def test_request_timeout_handling():
    provider = SlowTestLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(model_id="test-model-v1", messages=[msg], timeout=0.1)

    with pytest.raises(ProviderTimeoutError, match="timed out"):
        await provider.generate(req)


@pytest.mark.asyncio
async def test_generation_cancellation():
    provider = SlowTestLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(model_id="test-model-v1", messages=[msg], timeout=10.0)

    task = asyncio.create_task(provider.generate(req))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_streaming_cancellation():
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Stream test")
    req = LLMRequest(model_id="test-model-v1", messages=[msg], stream=True)

    received_events = []

    async def consume_stream():
        async for event in provider.stream(req):
            received_events.append(event)
            if len(received_events) >= 2:
                # Cancel task mid-stream
                asyncio.current_task().cancel()

    task = asyncio.create_task(consume_stream())

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(received_events) == 2
