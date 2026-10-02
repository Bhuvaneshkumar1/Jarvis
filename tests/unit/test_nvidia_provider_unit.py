"""
Unit Tests for NVIDIA NIM Provider Core Logic and Security (Batch 21).
"""

import pytest
from jarvis.llm.providers.nvidia import NVIDIAProvider
from jarvis.llm.exceptions import (
    LLMConfigurationError,
    redact_sensitive_str,
)
from jarvis.llm.contracts import LLMProviderState


def test_nvidia_provider_https_security_enforcement():
    # HTTP base_url for remote host must be rejected
    with pytest.raises(LLMConfigurationError, match="must use HTTPS"):
        NVIDIAProvider(base_url="http://remote.api.nvidia.com")

    # Localhost / 127.0.0.1 HTTP allowed for testing
    p_local = NVIDIAProvider(base_url="http://127.0.0.1:8000")
    assert p_local.base_url == "http://127.0.0.1:8000"


def test_nvidia_provider_headers_and_auth_redaction():
    provider = NVIDIAProvider(api_key="nvapi-test-secret-key-1234567890")
    headers = provider._get_headers()

    assert headers["Authorization"] == "Bearer nvapi-test-secret-key-1234567890"

    # Redactor must strip key from string representation
    err_msg = f"Failed with auth Bearer {provider.api_key}"
    cleaned = redact_sensitive_str(err_msg)
    assert "nvapi-test-secret-key-1234567890" not in cleaned
    assert "[REDACTED_SECRET]" in cleaned


@pytest.mark.asyncio
async def test_nvidia_provider_uninitialized_without_key():
    provider = NVIDIAProvider(api_key="YOUR_NVIDIA_API_KEY_HERE")
    await provider.initialize()

    assert provider.state == LLMProviderState.UNAVAILABLE
