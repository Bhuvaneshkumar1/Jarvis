"""
HTTP Transport Mock Integration Tests for NVIDIA NIM Provider (Batch 21).
Uses httpx.MockTransport for deterministic verification of OpenAPI chat completions,
SSE streaming, model discovery, tool calling, and error status code handling.
"""

import json
import pytest
import httpx

from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import (
    ChatMessage,
    LLMRequest,
    StreamEventType,
)
from jarvis.llm.providers.nvidia import NVIDIAProvider
from jarvis.llm.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.asyncio
async def test_mock_model_discovery():
    mock_models_json = {
        "object": "list",
        "data": [
            {"id": "meta/llama-3.3-70b-instruct", "object": "model", "created": 1700000000},
            {"id": "nvidia/nemotron-4-340b-instruct", "object": "model", "created": 1700000000},
        ],
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=mock_models_json)
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    provider = NVIDIAProvider(api_key="nvapi-mock-key", transport=transport)
    await provider.initialize()

    models = await provider.list_models()
    assert len(models) == 2
    model_ids = [m.model_id for m in models]
    assert "meta/llama-3.3-70b-instruct" in model_ids
    assert "nvidia/nemotron-4-340b-instruct" in model_ids


@pytest.mark.asyncio
async def test_mock_chat_completion_success():
    mock_completion_json = {
        "id": "chatcmpl-mock123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "meta/llama-3.3-70b-instruct",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! I am NVIDIA NIM Llama.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json=mock_completion_json)
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    provider = NVIDIAProvider(api_key="nvapi-mock-key", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    req = LLMRequest(model_id="meta/llama-3.3-70b-instruct", messages=[msg])

    res = await provider.generate(req)

    assert res.request_id == req.request_id
    assert res.provider_id == "nvidia"
    assert res.model_id == "meta/llama-3.3-70b-instruct"
    assert res.generated_content == "Hello! I am NVIDIA NIM Llama."
    assert res.finish_reason == "stop"
    assert res.usage is not None
    assert res.usage.total_tokens == 20


@pytest.mark.asyncio
async def test_mock_chat_completion_tool_calls():
    mock_tool_call_json = {
        "id": "chatcmpl-tool123",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-search-1",
                            "type": "function",
                            "function": {
                                "name": "search_database",
                                "arguments": json.dumps({"query": "AI architecture"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_tool_call_json)

    transport = httpx.MockTransport(handle_request)
    provider = NVIDIAProvider(api_key="nvapi-mock-key", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Search database")
    req = LLMRequest(
        model_id="meta/llama-3.3-70b-instruct",
        messages=[msg],
        tools=[{"name": "search_database"}],
    )

    res = await provider.generate(req)

    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_call_id == "call-search-1"
    assert res.tool_calls[0].tool_name == "search_database"
    assert res.tool_calls[0].arguments == {"query": "AI architecture"}
    assert res.tool_calls[0].status == "PENDING"


@pytest.mark.asyncio
async def test_mock_streaming_sse():
    sse_body = (
        'data: {"id": "chunk1", "choices": [{"delta": {"content": "Hello "}}]}\n\n'
        'data: {"id": "chunk2", "choices": [{"delta": {"content": "world!"}}]}\n\n'
        'data: {"id": "chunk3", "choices": [{"finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}\n\n'
        "data: [DONE]\n\n"
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    provider = NVIDIAProvider(api_key="nvapi-mock-key", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Stream test")
    req = LLMRequest(model_id="meta/llama-3.3-70b-instruct", messages=[msg], stream=True)

    events = []
    async for ev in provider.stream(req):
        events.append(ev)

    assert len(events) >= 4
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    text_deltas = [e.text_delta for e in events if e.event_type == StreamEventType.TEXT_DELTA]
    assert "".join(filter(None, text_deltas)) == "Hello world!"
    assert events[-1].event_type == StreamEventType.STREAM_COMPLETED


@pytest.mark.asyncio
async def test_mock_status_error_mapping():
    # 401 Auth Error
    def handle_401(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    provider_401 = NVIDIAProvider(api_key="invalid-key", transport=httpx.MockTransport(handle_401))
    await provider_401.initialize()
    msg = ChatMessage(role=MessageRole.USER, content="Hi")
    llm_req = LLMRequest(model_id="meta/llama-3.3-70b-instruct", messages=[msg])

    with pytest.raises(ProviderAuthenticationError):
        await provider_401.generate(llm_req)

    # 429 Rate Limit
    def handle_429(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "5"}, json={"error": "Rate limit"})

    provider_429 = NVIDIAProvider(api_key="nvapi-key", transport=httpx.MockTransport(handle_429))
    await provider_429.initialize()

    with pytest.raises(ProviderRateLimitError) as exc_info:
        await provider_429.generate(llm_req)
    assert exc_info.value.retry_after == 5.0

    # 500 Server Error
    def handle_500(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Server internal error"})

    provider_500 = NVIDIAProvider(api_key="nvapi-key", transport=httpx.MockTransport(handle_500))
    await provider_500.initialize()

    with pytest.raises(ProviderUnavailableError):
        await provider_500.generate(llm_req)
