"""
Normalized LLM Error Exception Hierarchy for JARVIS AI OS (Batch 20).
"""

import re
from typing import Optional
from jarvis.core.exceptions import JarvisError, ConfigurationError, AuthorizationError

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{30,}", re.IGNORECASE),
    re.compile(r"xox[bap]-[a-zA-Z0-9\-]+", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
]


def redact_sensitive_str(text: str) -> str:
    """Redacts API keys and auth tokens from error messages."""
    if not text:
        return text
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


class LLMError(JarvisError):
    """
    Base exception class for all LLM subsystem errors.
    """

    def __init__(
        self,
        message: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_retryable: bool = False,
        diagnostic_code: Optional[str] = None,
    ) -> None:
        self.raw_message = message
        self.message = redact_sensitive_str(message)
        self.provider_id = provider_id
        self.model_id = model_id
        self.request_id = request_id
        self.is_retryable = is_retryable
        self.diagnostic_code = diagnostic_code
        super().__init__(self.message)

    def __str__(self) -> str:
        ctx = []
        if self.provider_id:
            ctx.append(f"provider={self.provider_id}")
        if self.model_id:
            ctx.append(f"model={self.model_id}")
        if self.request_id:
            ctx.append(f"request_id={self.request_id}")
        ctx_str = f" [{', '.join(ctx)}]" if ctx else ""
        return f"{self.message}{ctx_str}"


class ProviderNotFoundError(LLMError):
    """Raised when a requested LLM provider is not registered or found."""

    pass


class ProviderUnavailableError(LLMError):
    """Raised when an LLM provider is offline, disabled, or in an unready state."""

    pass


class ProviderAuthenticationError(LLMError):
    """Raised when authentication with an LLM provider fails."""

    pass


class ProviderRateLimitError(LLMError):
    """Raised when an LLM provider rate limit / quota is exceeded."""

    def __init__(
        self,
        message: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
        diagnostic_code: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            provider_id=provider_id,
            model_id=model_id,
            request_id=request_id,
            is_retryable=True,
            diagnostic_code=diagnostic_code,
        )
        self.retry_after = retry_after


class ProviderTimeoutError(LLMError):
    """Raised when an LLM request exceeds its timeout threshold."""

    def __init__(
        self,
        message: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        request_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        diagnostic_code: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            provider_id=provider_id,
            model_id=model_id,
            request_id=request_id,
            is_retryable=True,
            diagnostic_code=diagnostic_code,
        )
        self.timeout_seconds = timeout_seconds


class ProviderConnectionError(LLMError):
    """Raised when network or connection to an LLM provider fails."""

    def __init__(
        self,
        message: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        request_id: Optional[str] = None,
        diagnostic_code: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            provider_id=provider_id,
            model_id=model_id,
            request_id=request_id,
            is_retryable=True,
            diagnostic_code=diagnostic_code,
        )


class ProviderResponseError(LLMError):
    """Raised when an LLM provider returns an unparseable or unexpected response."""

    pass


class InvalidLLMRequestError(LLMError, ValueError):
    """Raised when an LLM request payload fails validation checks."""

    pass


class UnsupportedCapabilityError(LLMError):
    """Raised when a request requires a model capability not supported by the model."""

    pass


class ContextLengthExceededError(LLMError):
    """Raised when prompt text exceeds model context window limits."""

    pass


class ContentFilteredError(LLMError):
    """Raised when model input/output is blocked by content safety filters."""

    pass


class LLMStreamInterruptedError(LLMError):
    """Raised when streaming output is abruptly terminated before completion."""

    pass


class LLMConfigurationError(LLMError, ConfigurationError):
    """Raised when LLM provider configuration is invalid or missing required options."""

    pass


class LLMInternalError(LLMError):
    """Raised for unexpected internal errors in the LLM subsystem."""

    pass


class LLMProviderInitializationError(LLMError, ConfigurationError):
    """Raised when local/remote LLM provider initialization or model loading fails."""

    pass


class LLMInferenceError(LLMError):
    """Raised when runtime inference execution fails."""

    pass


class LLMTimeoutError(ProviderTimeoutError):
    """Raised when local runtime inference times out."""

    pass


class LLMPrivacyViolationError(LLMError, AuthorizationError):
    """Raised when confidential or restricted data is routed to an unauthorized cloud provider."""

    pass
