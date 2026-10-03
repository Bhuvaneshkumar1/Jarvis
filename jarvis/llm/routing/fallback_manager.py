"""
Fallback Manager Subsystem for JARVIS LLM Router (Batch 24).

Evaluates error retryability, attempt budgets, local-only isolation, and fallback eligibility
between candidate providers without producing unbounded loops or duplicated side effects.
"""

import logging
from typing import Tuple, Optional
from jarvis.llm.contracts import LLMRequest, DataClassification
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.exceptions import (
    LLMError,
    InvalidLLMRequestError,
    LLMPrivacyViolationError,
    ProviderAuthenticationError,
    UnsupportedCapabilityError,
)

logger = logging.getLogger(__name__)

NON_RETRYABLE_EXCEPTIONS = (
    InvalidLLMRequestError,
    LLMPrivacyViolationError,
    ProviderAuthenticationError,
    UnsupportedCapabilityError,
)


class FallbackManager:
    """Evaluates fallback eligibility and tracks attempt history per request."""

    def __init__(self, max_attempts: int = 3, allow_fallback: bool = True):
        self.max_attempts = max_attempts
        self.allow_fallback = allow_fallback

    def is_error_retryable(self, error: Exception) -> bool:
        """Determines if an exception is retryable and eligible for provider fallback."""
        if isinstance(error, NON_RETRYABLE_EXCEPTIONS):
            return False

        if isinstance(error, LLMError):
            return getattr(error, "is_retryable", True)

        # Generic network or timeout errors are retryable
        return True

    def can_fallback(
        self,
        request: LLMRequest,
        current_attempt: int,
        error: Exception,
        next_provider: Optional[AbstractLLMProvider],
    ) -> Tuple[bool, str]:
        """
        Evaluates whether execution can fall back to the next candidate provider.
        Returns (allowed: bool, reason: str).
        """
        if not self.allow_fallback:
            return False, "Provider fallback is disabled in routing configuration."

        if current_attempt >= self.max_attempts:
            return False, f"Maximum provider attempts ({self.max_attempts}) reached for this request."

        if not self.is_error_retryable(error):
            return False, f"Error '{type(error).__name__}' is non-retryable and cannot trigger fallback."

        if not next_provider:
            return False, "No next eligible candidate provider available in routing chain."

        # Hard local-only privacy isolation check for fallback target
        if (
            request.local_only or request.data_classification in (DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED)
        ) and not next_provider.is_local:
            return False, (f"Fallback to external provider '{next_provider.provider_id}' blocked for local_only / {request.data_classification.value} data.")

        return True, f"Fallback approved to next provider '{next_provider.provider_id}'."
