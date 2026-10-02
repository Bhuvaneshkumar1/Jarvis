"""
Unit Tests for LLM Privacy, Data Classification, and Security Boundaries (Batch 20).
"""

import pytest
from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest, DataClassification
from jarvis.llm.test_provider import TestDeterministicLLMProvider
from jarvis.llm.exceptions import (
    LLMPrivacyViolationError,
    LLMError,
)


@pytest.mark.asyncio
async def test_restricted_and_confidential_data_blocked_from_cloud_providers():
    # Cloud provider (is_local = False)
    cloud_provider = TestDeterministicLLMProvider(provider_id="cloud_llm", is_local=False)
    await cloud_provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Secret financial record")

    confidential_req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        data_classification=DataClassification.CONFIDENTIAL,
    )
    with pytest.raises(LLMPrivacyViolationError, match="restricted to local providers"):
        await cloud_provider.generate(confidential_req)

    restricted_req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        data_classification=DataClassification.RESTRICTED,
    )
    with pytest.raises(LLMPrivacyViolationError, match="restricted to local providers"):
        await cloud_provider.generate(restricted_req)


@pytest.mark.asyncio
async def test_confidential_data_allowed_on_local_providers():
    # Local provider (is_local = True)
    local_provider = TestDeterministicLLMProvider(provider_id="local_llm", is_local=True)
    await local_provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Local private request")
    req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        data_classification=DataClassification.CONFIDENTIAL,
    )

    response = await local_provider.generate(req)
    assert response.generated_content is not None


@pytest.mark.asyncio
async def test_internal_data_sanitized_for_cloud_providers():
    cloud_provider = TestDeterministicLLMProvider(provider_id="cloud_llm", is_local=False)
    await cloud_provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Contact me at testuser@example.com with key TOKEN_PLACEHOLDER")
    req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        data_classification=DataClassification.INTERNAL,
    )

    # Validate privacy enforcer sanitizes the request payload
    sanitized = cloud_provider.privacy_enforcer.validate_and_sanitize_request(req, is_local_provider=False)

    assert "[REDACTED_EMAIL]" in sanitized.messages[0].content
    assert "[REDACTED_API_KEY]" in sanitized.messages[0].content


@pytest.mark.asyncio
async def test_tool_calling_security_boundary():
    """
    CRITICAL SECURITY CHECK:
    LLM Provider MUST return model-requested tool calls without executing any tool directly.
    """
    provider = TestDeterministicLLMProvider()
    await provider.initialize()

    msg = ChatMessage(role=MessageRole.USER, content="Please trigger_tool_call")
    req = LLMRequest(
        model_id="test-model-v1",
        messages=[msg],
        tools=[{"name": "system_command", "description": "Execute terminal command"}],
    )

    res = await provider.generate(req)

    # Tool call data is returned as an untrusted data payload
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "system_command"
    assert res.tool_calls[0].status == "PENDING"
    # No tool execution occurred within provider abstraction layer


def test_exception_secret_redaction():
    secret_msg = "Error connecting with key TOKEN_PLACEHOLDER and bearer token bearer 123456789012345678901234567890"
    err = LLMError(secret_msg)

    assert "TOKEN_PLACEHOLDER" not in str(err)
    assert "[REDACTED_SECRET]" in str(err)
