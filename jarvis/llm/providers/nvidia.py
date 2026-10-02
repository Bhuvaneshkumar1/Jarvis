"""
NVIDIA NIM Hosted Inference LLM Provider Implementation (Batch 21).
Communicates with NVIDIA's OpenAPI-compatible Hosted NIM Endpoints.
"""

import os
import time
import json
import uuid
import logging
import asyncio
from typing import List, Optional, Dict, Any, AsyncIterator, NoReturn

import httpx

from jarvis.core.enums import HealthState
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StreamEventType,
    LLMUsage,
    LLMToolCall,
    ModelCapability,
    LLMProviderState,
)
from jarvis.llm.exceptions import (
    LLMError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderConnectionError,
    ProviderResponseError,
    InvalidLLMRequestError,
    ContextLengthExceededError,
    LLMStreamInterruptedError,
    LLMConfigurationError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    redact_sensitive_str,
)

logger = logging.getLogger(__name__)


class NVIDIAProvider(AbstractLLMProvider):
    """
    NVIDIA NIM API Provider for Hosted LLM Inference.
    Base URL: https://integrate.api.nvidia.com
    Chat Completion: POST /v1/chat/completions
    Model Discovery: GET /v1/models
    """

    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com"
    DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"

    def __init__(
        self,
        provider_id: str = "nvidia",
        is_local: bool = False,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout_seconds: float = 60.0,
        http_client: Optional[httpx.AsyncClient] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        model_catalog_ttl: float = 3600.0,
        config: Optional[Any] = None,
    ) -> None:
        super().__init__(provider_id=provider_id, is_local=is_local)

        raw_url = (base_url or os.getenv("NVIDIA_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        if raw_url.endswith("/v1"):
            raw_url = raw_url[:-3]
        self.base_url = raw_url.rstrip("/")

        self._validate_base_url_security(self.base_url)

        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.default_model = default_model or os.getenv("NVIDIA_DEFAULT_MODEL") or self.DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds
        self.model_catalog_ttl = model_catalog_ttl
        self.config = config

        self._injected_client = http_client
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

        self._model_catalog_cache: Dict[str, ModelCapability] = {}
        self._catalog_last_updated: float = 0.0
        self._cache_lock = asyncio.Lock()

    def _validate_base_url_security(self, url: str) -> None:
        """Enforces HTTPS requirement for remote endpoints."""
        url_lower = url.lower()
        if not (url_lower.startswith("https://") or "127.0.0.1" in url_lower or "localhost" in url_lower):
            raise LLMConfigurationError(f"NVIDIA API base_url must use HTTPS for remote endpoint security: '{url}'")

    def _get_headers(self) -> Dict[str, str]:
        """Builds HTTP headers with Bearer token authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key and not self.api_key.startswith("YOUR_"):
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns or creates the underlying httpx.AsyncClient instance."""
        if self._injected_client is not None:
            return self._injected_client

        if self._client is None or self._client.is_closed:
            headers = self._get_headers()
            timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
            limits = httpx.Limits(max_connections=50, max_keepalive_connections=10)

            if self._transport is not None:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=timeout,
                    transport=self._transport,
                )
            else:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=timeout,
                    limits=limits,
                    verify=True,
                )
        return self._client

    async def initialize(self) -> None:
        """Initializes client and checks initial credential readiness."""
        self.state = LLMProviderState.INITIALIZING
        if not self.api_key or self.api_key.startswith("YOUR_"):
            logger.warning(f"NVIDIAProvider '{self.provider_id}' initialized without valid API key.")
            self.state = LLMProviderState.UNAVAILABLE
            return

        self.state = LLMProviderState.READY
        logger.info(f"NVIDIAProvider '{self.provider_id}' initialized cleanly.")

    async def close(self) -> None:
        """Gracefully closes HTTP client resources."""
        self.state = LLMProviderState.CLOSING
        if self._client is not None and not self._client.is_closed and self._injected_client is None:
            await self._client.aclose()
            self._client = None
        self.state = LLMProviderState.CLOSED
        logger.info(f"NVIDIAProvider '{self.provider_id}' closed.")

    async def health_check(self) -> HealthState:
        """Performs lightweight health check."""
        if not self.api_key or self.api_key.startswith("YOUR_"):
            return HealthState.UNHEALTHY

        if self.state not in (LLMProviderState.READY, LLMProviderState.DEGRADED):
            return HealthState.UNHEALTHY

        try:
            client = await self._get_client()
            res = await client.get("/v1/models", headers=self._get_headers())
            if res.status_code == 200:
                return HealthState.HEALTHY
            elif res.status_code in (401, 403):
                return HealthState.UNHEALTHY
            return HealthState.DEGRADED
        except Exception:
            return HealthState.UNHEALTHY

    async def list_models(self) -> List[ModelCapability]:
        """Lists available models from GET /v1/models with TTL caching."""
        await self.refresh_models(force=False)
        return list(self._model_catalog_cache.values())

    async def refresh_models(self, force: bool = False) -> None:
        """Refreshes the model catalogue from GET /v1/models."""
        now = time.time()
        if not force and self._model_catalog_cache and (now - self._catalog_last_updated) < self.model_catalog_ttl:
            return

        async with self._cache_lock:
            # Re-check inside lock
            if not force and self._model_catalog_cache and (now - self._catalog_last_updated) < self.model_catalog_ttl:
                return

            try:
                client = await self._get_client()
                response = await client.get("/v1/models", headers=self._get_headers())
                if response.status_code != 200:
                    self._handle_status_error(response)

                data = response.json()
                if not isinstance(data, dict) or "data" not in data:
                    raise ProviderResponseError("Invalid GET /v1/models response schema.")

                models_list = data.get("data", [])
                new_cache: Dict[str, ModelCapability] = {}

                for m in models_list:
                    if isinstance(m, dict) and "id" in m:
                        mid = str(m["id"]).strip()
                        cap = ModelCapability(
                            model_id=mid,
                            provider_id=self.provider_id,
                            supports_text_generation=True,
                            supports_streaming=True,
                            supports_structured_output=True,
                            supports_tool_calling=True,
                            context_window=(128000 if "vision" in mid or "3.3" in mid else 8192),
                            max_output_tokens=4096,
                        )
                        new_cache[mid] = cap

                self._model_catalog_cache = new_cache
                self._catalog_last_updated = now
                logger.info(f"NVIDIAProvider: discovered {len(new_cache)} models.")
            except Exception as ex:
                if isinstance(ex, LLMError):
                    raise
                self._handle_transport_error(ex)

    async def get_capabilities(self, model_id: str) -> ModelCapability:
        """Retrieves capabilities for model_id."""
        if not self._model_catalog_cache:
            try:
                await self.refresh_models(force=False)
            except Exception:
                pass

        cap = self._model_catalog_cache.get(model_id)
        if not cap:
            # Default capability profile for valid NVIDIA model names
            return ModelCapability(
                model_id=model_id,
                provider_id=self.provider_id,
                supports_text_generation=True,
                supports_streaming=True,
                supports_structured_output=True,
                supports_tool_calling=True,
                context_window=8192,
                max_output_tokens=4096,
            )
        return cap

    def _build_payload(self, request: LLMRequest, stream: bool = False) -> Dict[str, Any]:
        """Serializes LLMRequest to NVIDIA OpenAPI chat completion schema."""
        messages = []
        if request.system_instructions:
            messages.append({"role": "system", "content": request.system_instructions})

        for msg in request.messages:
            m_dict: Dict[str, Any] = {
                "role": msg.role.value.lower(),
                "content": msg.content,
            }
            if msg.name:
                m_dict["name"] = msg.name
            if msg.tool_call_id:
                m_dict["tool_call_id"] = msg.tool_call_id
            messages.append(m_dict)

        payload: Dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "temperature": request.temperature,
            "stream": stream,
        }

        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.response_format:
            payload["response_format"] = request.response_format
        if request.tools:
            payload["tools"] = request.tools

        return payload

    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        """Executes synchronous/non-streaming chat completion request."""
        start_time = time.time()
        payload = self._build_payload(request, stream=False)

        try:
            client = await self._get_client()
            response = await client.post(
                "/v1/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=request.timeout,
            )

            if response.status_code != 200:
                self._handle_status_error(response, request_id=request.request_id, model_id=request.model_id)

            data = response.json()
            latency = round(time.time() - start_time, 4)
            return self._parse_chat_response(data, request, latency)

        except Exception as ex:
            if isinstance(ex, LLMError):
                raise
            self._handle_transport_error(ex, request_id=request.request_id, model_id=request.model_id)

    async def _do_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Executes streaming chat completion request yielding LLMStreamEvents."""
        payload = self._build_payload(request, stream=True)

        yield LLMStreamEvent(
            request_id=request.request_id,
            event_type=StreamEventType.STREAM_STARTED,
        )

        try:
            client = await self._get_client()
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=request.timeout,
            ) as response:
                if response.status_code != 200:
                    # Read error body text
                    err_body = await response.aread()
                    self._handle_status_error(
                        response,
                        body_override=err_body.decode("utf-8", errors="ignore"),
                        request_id=request.request_id,
                        model_id=request.model_id,
                    )

                accumulated_text = ""
                finish_reason = None
                usage_info: Optional[LLMUsage] = None

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if choices and isinstance(choices, list):
                        c0 = choices[0]
                        delta = c0.get("delta", {})
                        content_delta = delta.get("content")
                        if content_delta:
                            accumulated_text += content_delta
                            yield LLMStreamEvent(
                                request_id=request.request_id,
                                event_type=StreamEventType.TEXT_DELTA,
                                text_delta=content_delta,
                            )

                        # Handle tool call delta if present
                        tool_calls_delta = delta.get("tool_calls")
                        if tool_calls_delta and isinstance(tool_calls_delta, list):
                            for tc_d in tool_calls_delta:
                                fn = tc_d.get("function", {})
                                yield LLMStreamEvent(
                                    request_id=request.request_id,
                                    event_type=StreamEventType.TOOL_CALL_DELTA,
                                    tool_call_delta=LLMToolCall(
                                        tool_call_id=tc_d.get("id", f"call-{uuid.uuid4().hex[:8]}"),
                                        tool_name=fn.get("name", "tool"),
                                        arguments=fn.get("arguments", {}),
                                    ),
                                )

                        if c0.get("finish_reason"):
                            finish_reason = c0.get("finish_reason")

                    if chunk.get("usage"):
                        u_dict = chunk["usage"]
                        usage_info = LLMUsage(
                            input_tokens=u_dict.get("prompt_tokens", 0),
                            output_tokens=u_dict.get("completion_tokens", 0),
                            total_tokens=u_dict.get("total_tokens", 0),
                        )
                        yield LLMStreamEvent(
                            request_id=request.request_id,
                            event_type=StreamEventType.USAGE_UPDATE,
                            usage=usage_info,
                        )

                yield LLMStreamEvent(
                    request_id=request.request_id,
                    event_type=StreamEventType.STREAM_COMPLETED,
                    finish_reason=finish_reason or "stop",
                    usage=usage_info,
                )

        except asyncio.CancelledError:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_CANCELLED,
            )
            raise
        except Exception as ex:
            if isinstance(ex, LLMError):
                yield LLMStreamEvent(
                    request_id=request.request_id,
                    event_type=StreamEventType.STREAM_FAILED,
                    error_message=str(ex),
                )
                raise
            err_msg = redact_sensitive_str(str(ex))
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message=err_msg,
            )
            raise LLMStreamInterruptedError(
                f"NVIDIA stream interrupted: {err_msg}",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            ) from ex

    def _parse_chat_response(self, data: Dict[str, Any], request: LLMRequest, latency: float) -> LLMResponse:
        """Parses POST /v1/chat/completions JSON payload into LLMResponse."""
        if not isinstance(data, dict):
            raise ProviderResponseError(
                "NVIDIA chat completion payload is not a JSON object.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise ProviderResponseError(
                "NVIDIA chat completion response missing 'choices' array.",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        c0 = choices[0]
        message = c0.get("message", {})
        content = message.get("content")
        finish_reason = c0.get("finish_reason", "stop")

        # Parse tool calls into LLMToolCall list if returned by model
        tool_calls: List[LLMToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        if isinstance(raw_tool_calls, list):
            for idx, tc in enumerate(raw_tool_calls):
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {"raw_args": fn_args}

                    tool_calls.append(
                        LLMToolCall(
                            tool_call_id=tc.get("id", f"call-{idx}-{request.request_id[:6]}"),
                            tool_name=fn.get("name", "unknown_tool"),
                            arguments=fn_args if isinstance(fn_args, dict) else {},
                            call_index=idx,
                        )
                    )

        # Parse structured output if requested and valid JSON string returned
        structured_output: Optional[Dict[str, Any]] = None
        if request.response_format and content:
            try:
                structured_output = json.loads(content)
            except Exception:
                logger.warning("Failed to parse structured JSON output from NVIDIA model response.")

        # Parse usage metadata
        usage: Optional[LLMUsage] = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = LLMUsage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )

        return LLMResponse(
            request_id=request.request_id,
            provider=self.provider_id,
            model=request.model_id,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            latency=latency,
            structured_output=structured_output,
            tool_calls=tool_calls,
            provider_request_id=data.get("id"),
        )

    def _handle_status_error(
        self,
        response: httpx.Response,
        body_override: Optional[str] = None,
        request_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> NoReturn:
        """Maps HTTP status error codes to normalized LLM exception hierarchy."""
        status = response.status_code
        msg = body_override if body_override is not None else response.text
        msg = redact_sensitive_str(msg)

        if status == 401:
            raise ProviderAuthenticationError(
                f"NVIDIA API authentication failed (HTTP 401): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status == 403:
            raise ProviderAuthenticationError(
                f"NVIDIA API access forbidden (HTTP 403): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status in (404, 410):
            raise ProviderNotFoundError(
                f"NVIDIA model or endpoint not found / expired (HTTP {status}): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status == 408:
            raise ProviderTimeoutError(
                f"NVIDIA API request timeout (HTTP 408): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status == 413:
            raise ContextLengthExceededError(
                f"NVIDIA API payload / context length exceeded (HTTP 413): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status == 422:
            raise InvalidLLMRequestError(
                f"NVIDIA API unprocessable request parameters (HTTP 422): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        elif status == 429:
            retry_after_str = response.headers.get("retry-after")
            retry_after = float(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None
            raise ProviderRateLimitError(
                f"NVIDIA API rate limit exceeded (HTTP 429): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
                retry_after=retry_after,
            )
        elif status in (500, 502, 503, 504):
            raise ProviderUnavailableError(
                f"NVIDIA API server error (HTTP {status}): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )
        else:
            raise ProviderResponseError(
                f"NVIDIA API error (HTTP {status}): {msg}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            )

    def _handle_transport_error(
        self,
        exc: Exception,
        request_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> NoReturn:
        """Maps httpx transport and network exceptions to normalized LLM exceptions."""
        safe_err = redact_sensitive_str(str(exc))
        if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
            raise ProviderTimeoutError(
                f"NVIDIA network timeout: {safe_err}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            ) from exc

        if isinstance(exc, httpx.NetworkError):
            raise ProviderConnectionError(
                f"NVIDIA network connection error: {safe_err}",
                provider_id=self.provider_id,
                model_id=model_id,
                request_id=request_id,
            ) from exc

        raise ProviderResponseError(
            f"NVIDIA operational failure: {safe_err}",
            provider_id=self.provider_id,
            model_id=model_id,
            request_id=request_id,
        ) from exc
