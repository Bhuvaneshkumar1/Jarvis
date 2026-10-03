"""
Routing Policy Engine for JARVIS LLM Router (Batch 24).

Enforces data classification privacy boundaries, local-only processing constraints,
and security policy rules prior to LLM candidate selection and provider execution.
"""

import logging
from typing import Tuple, Optional
from jarvis.llm.contracts import LLMRequest, DataClassification
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.privacy import LLMPrivacyEnforcer

logger = logging.getLogger(__name__)


class RoutingPolicyEngine:
    """Enforces data privacy rules and hard routing policy constraints."""

    def __init__(self, privacy_enforcer: Optional[LLMPrivacyEnforcer] = None):
        self.privacy_enforcer = privacy_enforcer or LLMPrivacyEnforcer()

    def validate_request_policy(self, request: LLMRequest) -> None:
        """
        Validates request against overall application privacy and security policy.
        Raises LLMPrivacyViolationError if request violates basic data bounds.
        """
        # Sanitization & basic validation via central privacy enforcer (is_local_provider=True for initial policy check)
        self.privacy_enforcer.validate_and_sanitize_request(request, is_local_provider=True)

    def is_provider_allowed_by_privacy(self, request: LLMRequest, provider: AbstractLLMProvider) -> Tuple[bool, str]:
        """
        Evaluates whether a specific provider is allowed for the given request's data classification.
        - CONFIDENTIAL, RESTRICTED, or request.local_only == True MUST ONLY use local providers (is_local == True).
        - PUBLIC and INTERNAL can use local or external providers.
        """
        if request.local_only and not provider.is_local:
            return False, f"Provider '{provider.provider_id}' is external, but request requires local_only processing."

        if request.data_classification in (DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED) and not provider.is_local:
            return False, (f"Provider '{provider.provider_id}' is external, but data classification is {request.data_classification.value}.")

        return True, "Provider privacy policy check passed."
