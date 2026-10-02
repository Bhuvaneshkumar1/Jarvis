"""
HTTP Transport Mock Integration Tests for OpenRouter Provider (Batch 22).
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
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.asyncio
async def test_mock_model_discovery():
    mock_models_json = {
        "data": [
            {
                "id": "openai/gpt-4o",
                "name": "OpenAI: GPT-4o",
                "context_length": 128000,
                "pricing": {"prompt": "0.000005", "completion": "0.000015"},
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Anthropic: Claude 3.5 Sonnet",
                "context_length": 200000,
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json=mock_models_json)

    transport = httpx.MockTransport(handler)
    provider = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport)
    await provider.initialize()

    models = await provider.list_models()
    assert len(models) == 2
    assert models[0].model_id == "openai/gpt-4o"
    assert models[0].context_window == 128000
    assert models[1].model_id == "anthropic/claude-3.5-sonnet"

    await provider.close()


@pytest.mark.asyncio
async def test_mock_chat_completion_success():
    mock_chat_json = {
        "id": "gen-12345",
        "model": "openai/gpt-4o-mini",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "JARVIS online."},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "openai/gpt-4o-mini"
        assert payload["messages"][0]["content"] == "Status"
        return httpx.Response(200, json=mock_chat_json)

    transport = httpx.MockTransport(handler)
    provider = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Status")
    req = LLMRequest(model_id="openai/gpt-4o-mini", messages=[msg])

    res = await provider.generate(req)
    assert res.request_id == req.request_id
    assert res.provider_id == "openrouter"
    assert res.model_id == "openai/gpt-4o-mini"
    assert res.content == "JARVIS online."
    assert res.usage.total_tokens == 16
    assert res.latency > 0.0

    await provider.close()


@pytest.mark.asyncio
async def test_mock_tool_calling_normalization():
    mock_tool_json = {
        "id": "gen-9999",
        "model": "anthropic/claude-3.5-sonnet",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "search_files",
                                "arguments": '{"query": "config"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_tool_json)

    transport = httpx.MockTransport(handler)
    provider = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Find config files")
    req = LLMRequest(
        model_id="anthropic/claude-3.5-sonnet",
        messages=[msg],
        tools=[{"name": "search_files", "description": "Searches disk"}],
    )

    res = await provider.generate(req)
    assert len(res.tool_calls) == 1
    tc = res.tool_calls[0]
    assert tc.tool_call_id == "call_abc123"
    assert tc.tool_name == "search_files"
    assert tc.arguments == {"query": "config"}
    assert tc.status == "PENDING"  # Tool execution isolated from provider

    await provider.close()


@pytest.mark.asyncio
async def test_mock_streaming_sse():
    sse_body = (
        'data: {"id": "chunk1", "choices": [{"delta": {"content": "Hello "}}]}\n\n'
        'data: {"id": "chunk2", "choices": [{"delta": {"content": "world!"}}]}\n\n'
        'data: {"id": "chunk3", "choices": [{"finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    provider = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport)
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Say hello")
    req = LLMRequest(model_id="openai/gpt-4o-mini", messages=[msg], stream=True)

    events = []
    async for event in provider.generate_stream(req):
        events.append(event)

    assert len(events) >= 3
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    text_deltas = [e.text_delta for e in events if e.event_type == StreamEventType.TEXT_DELTA]
    assert "".join(text_deltas) == "Hello world!"
    assert events[-1].event_type == StreamEventType.STREAM_COMPLETED

    await provider.close()


@pytest.mark.asyncio
async def test_mock_status_error_mapping():
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport_401 = httpx.MockTransport(handler_401)
    provider_401 = OpenRouterProvider(api_key="sk-or-v1-badkey", transport=transport_401)
    await provider_401.initialize()

    req = LLMRequest(model_id="openai/gpt-4o-mini", messages=[ChatMessage(role=MessageRole.USER, content="Hi")])
    with pytest.raises(ProviderAuthenticationError, match="authentication failed"):
        await provider_401.generate(req)
    await provider_401.close()

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "5"}, json={"error": "Rate limit"})

    transport_429 = httpx.MockTransport(handler_429)
    provider_429 = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport_429)
    await provider_429.initialize()

    with pytest.raises(ProviderRateLimitError) as exc_info:
        await provider_429.generate(req)
    assert exc_info.value.retry_after == 5.0
    await provider_429.close()

    def handler_503(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "Overloaded"})

    transport_503 = httpx.MockTransport(handler_503)
    provider_503 = OpenRouterProvider(api_key="sk-or-v1-mock", transport=transport_503)
    await provider_503.initialize()

    with pytest.raises(ProviderUnavailableError, match="server error"):
        await provider_503.generate(req)
    await provider_503.close()
