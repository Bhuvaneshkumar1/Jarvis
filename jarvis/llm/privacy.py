"""
Privacy & Data Classification Enforcer for LLM Provider Subsystem (Batch 20).
"""

import logging
from typing import Optional
from jarvis.core.privacy import PrivacyEngine
from jarvis.llm.contracts import LLMRequest, DataClassification
from jarvis.llm.exceptions import LLMPrivacyViolationError

logger = logging.getLogger(__name__)


class LLMPrivacyEnforcer:
    """
    Enforces JARVIS Privacy Policy on LLM Request payloads prior to provider dispatch.
    """

    def __init__(self, privacy_engine: Optional[PrivacyEngine] = None) -> None:
        self.privacy_engine = privacy_engine or PrivacyEngine()

    def validate_and_sanitize_request(self, request: LLMRequest, is_local_provider: bool) -> LLMRequest:
        """
        Validates request data classification and sanitizes payload content if required.
        Raises LLMPrivacyViolationError if policy is violated.
        """
        classification = request.data_classification

        # Fail closed for invalid/unrecognized classification
        if not isinstance(classification, DataClassification):
            try:
                classification = DataClassification(str(classification).upper())
            except ValueError:
                raise LLMPrivacyViolationError(
                    f"Unknown data classification '{request.data_classification}'. Access denied.",
                    request_id=request.request_id,
                    model_id=request.model_id,
                )

        # CONFIDENTIAL or RESTRICTED requests MUST use local processing path
        if not is_local_provider and classification in (DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED):
            raise LLMPrivacyViolationError(
                f"Data classification '{classification.value}' is restricted to local providers and cannot be routed to external cloud provider.",
                request_id=request.request_id,
                model_id=request.model_id,
            )

        # If sending INTERNAL data to external cloud provider, aggressively sanitize content
        if not is_local_provider and classification == DataClassification.INTERNAL:
            sanitized_messages = []
            for msg in request.messages:
                cleaned_content, _ = self.privacy_engine.filter_text(msg.content)
                sanitized_messages.append(msg.model_copy(update={"content": cleaned_content}))

            cleaned_system = None
            if request.system_instructions:
                cleaned_system, _ = self.privacy_engine.filter_text(request.system_instructions)

            return request.model_copy(
                update={
                    "messages": sanitized_messages,
                    "system_instructions": cleaned_system,
                }
            )

        return request
