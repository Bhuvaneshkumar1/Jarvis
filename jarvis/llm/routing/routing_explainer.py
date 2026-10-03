"""
Routing Explainer Subsystem for JARVIS LLM Router (Batch 24).

Generates safe, sanitized diagnostic routing explanations for observability and auditing,
without exposing prompts, credentials, or sensitive filesystem paths.
"""

import logging
from typing import List, Dict, Any, Optional
from jarvis.llm.contracts import LLMRequest, TaskCategory, RoutingProfile
from jarvis.llm.routing.candidate_selector import CandidateEvaluationRecord

logger = logging.getLogger(__name__)


class RoutingExplainer:
    """Produces sanitized routing decision explanations."""

    @staticmethod
    def create_explanation(
        request: LLMRequest,
        task_category: TaskCategory,
        profile: RoutingProfile,
        evaluations: List[CandidateEvaluationRecord],
        selected_provider_id: Optional[str],
        selected_model_id: Optional[str],
        attempts: List[Dict[str, Any]],
        outcome: str,
    ) -> Dict[str, Any]:
        """Constructs a sanitized routing record explanation."""
        eligible = [e.to_dict() for e in evaluations if e.is_eligible]
        excluded = [e.to_dict() for e in evaluations if not e.is_eligible]

        explanation: Dict[str, Any] = {
            "request_id": request.request_id,
            "task_category": task_category.value,
            "data_classification": request.data_classification.value,
            "local_only": request.local_only,
            "profile": profile.value,
            "selected_provider": selected_provider_id,
            "selected_model": selected_model_id,
            "eligible_candidates_count": len(eligible),
            "excluded_candidates_count": len(excluded),
            "evaluations": {
                "eligible": eligible,
                "excluded": excluded,
            },
            "attempts_count": len(attempts),
            "attempts": attempts,
            "fallback_occurred": len(attempts) > 1,
            "outcome": outcome,
        }
        return explanation
