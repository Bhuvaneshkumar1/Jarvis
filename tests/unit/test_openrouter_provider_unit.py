"""
Unit Tests for OpenRouter Provider Core Logic and Security (Batch 22).
"""

import pytest
from jarvis.llm.providers.openrouter import OpenRouterProvider
from jarvis.llm.exceptions import (
    LLMConfigurationError,
    redact_sensitive_str,
)
from jarvis.llm.contracts import LLMProviderState


def test_openrouter_provider_https_security_enforcement():
    # HTTP base_url for remote host must be rejected
    with pytest.raises(LLMConfigurationError, match="must use HTTPS"):
        OpenRouterProvider(base_url="http://remote.openrouter.ai")

    # Localhost / 127.0.0.1 HTTP allowed for testing
    provider = OpenRouterProvider(base_url="http://127.0.0.1:8000")
    assert provider.base_url == "http://127.0.0.1:8000"


def test_openrouter_provider_header_formatting():
    provider = OpenRouterProvider(
        api_key="sk-or-v1-testkey123",
        site_url="https://jarvis.ai",
        site_name="JARVIS Operating System",
    )
    headers = provider._get_headers()
    assert headers["Authorization"] == "Bearer sk-or-v1-testkey123"
    assert headers["HTTP-Referer"] == "https://jarvis.ai"
    assert headers["X-Title"] == "JARVIS Operating System"


@pytest.mark.asyncio
async def test_openrouter_provider_unconfigured_state():
    provider = OpenRouterProvider(api_key=None)
    await provider.initialize()
    assert provider.state == LLMProviderState.UNAVAILABLE
    await provider.close()


def test_openrouter_secret_key_redaction():
    secret = "sk-or-v1-dummykey123456"
    log_line = f"Error with Authorization: Bearer {secret}"
    redacted = redact_sensitive_str(log_line)
    assert secret not in redacted
    assert "[REDACTED_SECRET]" in redacted
