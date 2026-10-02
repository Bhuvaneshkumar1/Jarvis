# OpenRouter Provider Integration Architecture (Batch 22)

## 1. Subsystem Overview

The `OpenRouterProvider` (`jarvis/llm/providers/openrouter.py`) integrates JARVIS with OpenRouter's OpenAPI-compatible unified multi-model inference gateway (`https://openrouter.ai/api/v1`). It inherits from `AbstractLLMProvider` and provides model catalog discovery, non-streaming chat completions, Server-Sent Events (SSE) streaming, tool-call payload parsing, structured output handling, and HTTP status code normalization.

---

## 2. Configuration & Initialization

| Setting / Env Variable | Description | Default Value |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | Bearer token credential | `None` |
| `OPENROUTER_BASE_URL` | OpenRouter OpenAPI base URL | `https://openrouter.ai/api/v1` |
| `OPENROUTER_HTTP_REFERER` | Site URL for `HTTP-Referer` header | `None` |
| `OPENROUTER_APP_TITLE` | App Title for `X-Title` header | `None` |
| `OPENROUTER_DEFAULT_MODEL` | Default fallback model ID | `openai/gpt-4o-mini` |

### Security & Endpoint Validation
- Enforces HTTPS for remote `base_url` endpoints unless bound to loopback `127.0.0.1` or `localhost`.
- API keys are redacted from log outputs and exceptions via `redact_sensitive_str`.

---

## 3. Key Capabilities & Endpoints

- **Model Discovery (`GET /v1/models`)**: Fetches model catalog metadata, including context lengths, architecture capabilities, and pricing. Results are TTL-cached.
- **Chat Completion (`POST /v1/chat/completions`)**: Submits prompt messages, system instructions, temperature, top-p, stop sequences, and tool definitions.
- **Streaming (`stream=True`)**: Emits `LLMStreamEvent` incremental events (`STREAM_STARTED`, `TEXT_DELTA`, `TOOL_CALL_DELTA`, `STREAM_COMPLETED`).
- **Tool Calling**: Parses returned `tool_calls` payloads into `LLMToolCall` objects with `status="PENDING"`. Does **NOT** execute tools directly within the provider (security isolation).
- **Privacy Enforcement**: Integrated with `LLMPrivacyEnforcer`. Blocks `CONFIDENTIAL` or `RESTRICTED` data from cloud transmission.

---

## 4. Error Mapping Matrix

| Status / Exception | Mapped LLM Exception | Retryable |
| :--- | :--- | :--- |
| HTTP 400 / 422 | `InvalidLLMRequestError` | No |
| HTTP 401 / 403 | `ProviderAuthenticationError` | No |
| HTTP 404 / 410 | `ProviderNotFoundError` | No |
| HTTP 408 | `ProviderTimeoutError` | Yes |
| HTTP 413 | `ContextLengthExceededError` | No |
| HTTP 429 | `ProviderRateLimitError` | Yes |
| HTTP 500 / 502 / 503 / 504 | `ProviderUnavailableError` | Yes |
| `httpx.TimeoutException` | `ProviderTimeoutError` | Yes |
| `httpx.NetworkError` | `ProviderConnectionError` | Yes |

---

## 5. Usage Example

```python
import asyncio
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.contracts import LLMRequest, ChatMessage
from jarvis.core.enums import MessageRole


async def main():
    provider = OpenRouterProvider(api_key="sk-or-v1-YOUR_KEY")
    await provider.initialize()

    # Discover models
    models = await provider.list_models()
    print(f"Discovered {len(models)} OpenRouter models.")

    # Request completion
    request = LLMRequest(model_id="openai/gpt-4o-mini", messages=[ChatMessage(role=MessageRole.USER, content="Hello OpenRouter!")], max_tokens=50)

    response = await provider.generate(request)
    print(f"Response: {response.content}")

    await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
```
