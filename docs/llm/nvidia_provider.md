# JARVIS LLM Provider Documentation — NVIDIA NIM Integration (Batch 21)

## 1. Overview
The **NVIDIA NIM Provider** (`NVIDIAProvider`) connects JARVIS to NVIDIA's Hosted LLM Inference API endpoints (`https://integrate.api.nvidia.com`).

It implements the unified Batch 20 `AbstractLLMProvider` contract, enabling text generation, streaming, model discovery, capability detection, structured JSON outputs, and tool-call payload parsing without forcing higher-level orchestrators or agents to handle vendor-specific APIs.

---

## 2. Architecture & Components

```text
JarvisApplication / LLMSubsystem
              │
              ▼
    LLMProviderRegistry / Factory
              │
              ▼
       NVIDIAProvider (jarvis.llm.providers.nvidia)
        ├── Auth Header Generator (Bearer NVIDIA_API_KEY)
        ├── GET /v1/models (Model Discovery & TTL Catalog Cache)
        ├── POST /v1/chat/completions (Inference & SSE Streaming)
        ├── LLMPrivacyEnforcer (Data Classification & Prompt Sanitization)
        └── Error Normalizer (HTTP status -> Batch 20 LLM exceptions)
```

### Module Location
- `jarvis/llm/providers/nvidia.py`: Core `NVIDIAProvider` implementation.
- `jarvis/llm/providers/__init__.py`: Provider package exports.

---

## 3. Configuration & Credential Resolution

### Environment Variables (.env / .env.example)
```bash
NVIDIA_API_KEY=YOUR_NVIDIA_API_KEY_HERE
NVIDIA_BASE_URL=https://integrate.api.nvidia.com
NVIDIA_DEFAULT_MODEL=meta/llama-3.3-70b-instruct
NVIDIA_TIMEOUT_SECONDS=60
NVIDIA_ENABLED=false
```

### Security & Secret Protection
- **Resolution Path**: `SecretsManager` -> `os.environ["NVIDIA_API_KEY"]`.
- **Anti-Leakage**: API keys are redacted from exception messages, representation strings, and logs using `redact_sensitive_str`.
- **HTTPS Enforcement**: HTTPS is mandatory for remote endpoints. Unencrypted HTTP is rejected unless connecting to `127.0.0.1` / `localhost` for local testing.

---

## 4. Model Discovery & Capability Detection

- **Endpoint**: `GET /v1/models`
- **Caching**: Discovered models are cached in `_model_catalog_cache` with a default TTL of 3600 seconds. Call `refresh_models(force=True)` to force a refresh.
- **Capabilities**: Requests check `supports_streaming`, `supports_structured_output`, `supports_tool_calling`, and `context_window` limits against model capability profiles before transmission.

---

## 5. Inference & Streaming

### Chat Completions (`POST /v1/chat/completions`)
```python
from jarvis.llm.contracts import LLMRequest, ChatMessage
from jarvis.core.enums import MessageRole
from jarvis.llm.providers.nvidia import NVIDIAProvider

provider = NVIDIAProvider(api_key="your_api_key")
await provider.initialize()

req = LLMRequest(
    model_id="meta/llama-3.3-70b-instruct",
    messages=[ChatMessage(role=MessageRole.USER, content="Hello JARVIS")],
    temperature=0.7,
    max_tokens=100,
)

response = await provider.generate(req)
print(response.generated_content)
```

### Server-Sent Events (SSE) Streaming
When `req.stream = True`, `provider.stream(req)` yields normalized `LLMStreamEvent` events (`STREAM_STARTED`, `TEXT_DELTA`, `TOOL_CALL_DELTA`, `USAGE_UPDATE`, `STREAM_COMPLETED`).

---

## 6. Error Handling & Status Code Normalization

| HTTP Status | NVIDIA Response Context | Normalized JARVIS Exception |
|---|---|---|
| **400** | Invalid parameters / malformed payload | `InvalidLLMRequestError` / `ProviderResponseError` |
| **401 / 403** | Invalid API key / missing permissions | `ProviderAuthenticationError` |
| **404 / 410** | Model not found or EOL / model expired | `ProviderNotFoundError` |
| **408** | Request timeout | `ProviderTimeoutError` |
| **413** | Context length / payload cap exceeded | `ContextLengthExceededError` |
| **422** | Unprocessable schema parameters | `InvalidLLMRequestError` / `UnsupportedCapabilityError` |
| **429** | Rate limit / quota exceeded | `ProviderRateLimitError` |
| **500 / 502 / 503 / 504** | Remote server / gateway failure | `ProviderUnavailableError` / `ProviderResponseError` |

---

## 7. Security & Privacy Controls

- **Data Classification**: `LLMPrivacyEnforcer` enforces that `CONFIDENTIAL` or `RESTRICTED` request payloads CANNOT be routed to `NVIDIAProvider` (`is_local=False`).
- **Tool Execution Boundary**: Tool calls returned by NVIDIA models are parsed into `LLMToolCall` objects with `status="PENDING"`. The provider abstraction **NEVER** executes tools directly; execution remains governed by local JARVIS policy, approval, and verification engines.

---

## 8. Test Execution Commands

```bash
# Run unit & security tests
pytest tests/unit/test_nvidia_provider_unit.py -v

# Run HTTP transport mock tests (no network calls required)
pytest tests/unit/test_nvidia_provider_mock_http.py -v

# Run opt-in live API integration tests (requires NVIDIA_API_KEY)
pytest tests/integration/test_nvidia_live_api.py -v
```
