"""
Candidate Selector Subsystem for JARVIS LLM Router (Batch 24).

Filters and ranks eligible (provider_id, model_id) candidates using hard constraints
followed by profile-driven soft preferences and deterministic tie-breaking.
"""

import logging
from typing import List, Tuple, Dict, Any, Optional

from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.contracts import (
    LLMRequest,
    ModelCapability,
    RoutingProfile,
    LLMProviderState,
)
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.routing.routing_policy import RoutingPolicyEngine
from jarvis.llm.routing.capability_matcher import CapabilityMatcher
from jarvis.llm.routing.routing_metrics import RoutingMetricsTracker

logger = logging.getLogger(__name__)


class CandidateEvaluationRecord:
    """Diagnostic evaluation output for candidate filtering explainability."""

    def __init__(self, provider_id: str, model_id: str, is_eligible: bool, reason: str):
        self.provider_id = provider_id
        self.model_id = model_id
        self.is_eligible = is_eligible
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "is_eligible": self.is_eligible,
            "reason": self.reason,
        }


class CandidateSelector:
    """Selects and ranks candidate providers and models for an LLMRequest."""

    def __init__(
        self,
        registry: LLMProviderRegistry,
        policy_engine: Optional[RoutingPolicyEngine] = None,
        metrics_tracker: Optional[RoutingMetricsTracker] = None,
    ):
        self.registry = registry
        self.policy_engine = policy_engine or RoutingPolicyEngine()
        self.metrics_tracker = metrics_tracker or RoutingMetricsTracker()

    async def select_candidates(
        self,
        request: LLMRequest,
        profile: RoutingProfile = RoutingProfile.BALANCED,
    ) -> Tuple[List[Tuple[AbstractLLMProvider, str]], List[CandidateEvaluationRecord]]:
        """
        Builds an ordered candidate chain of (provider, model_id) tuples and diagnostic evaluations.
        """
        all_providers = self.registry.list_providers()
        evaluations: List[CandidateEvaluationRecord] = []
        eligible_candidates: List[Tuple[AbstractLLMProvider, ModelCapability]] = []

        for provider in all_providers:
            # 1. Privacy Policy Check
            privacy_ok, privacy_reason = self.policy_engine.is_provider_allowed_by_privacy(request, provider)
            if not privacy_ok:
                evaluations.append(
                    CandidateEvaluationRecord(
                        provider_id=provider.provider_id,
                        model_id="*",
                        is_eligible=False,
                        reason=privacy_reason,
                    )
                )
                continue

            # 2. Health & State Check
            if provider.state in (LLMProviderState.UNAVAILABLE, LLMProviderState.CLOSED, LLMProviderState.FAILED):
                evaluations.append(
                    CandidateEvaluationRecord(
                        provider_id=provider.provider_id,
                        model_id="*",
                        is_eligible=False,
                        reason=f"Provider in unusable state ({provider.state.value}).",
                    )
                )
                continue

            # Check explicit requested provider restriction
            if request.preferred_provider and request.preferred_provider.strip().lower() != provider.provider_id.lower():
                # If preferred provider is explicitly specified as a hard constraint by metadata/request
                pass

            # 3. Model Capabilities Inspection
            try:
                models = await provider.list_models()
            except Exception as e:
                logger.warning(f"Could not list models for provider '{provider.provider_id}': {e}")
                evaluations.append(
                    CandidateEvaluationRecord(
                        provider_id=provider.provider_id,
                        model_id="*",
                        is_eligible=False,
                        reason=f"Failed to list models: {e}",
                    )
                )
                continue

            for cap in models:
                # 4. Capability Matching
                cap_ok, missing = CapabilityMatcher.evaluate_capability(cap, request)
                if not cap_ok:
                    evaluations.append(
                        CandidateEvaluationRecord(
                            provider_id=provider.provider_id,
                            model_id=cap.model_id,
                            is_eligible=False,
                            reason=f"Missing required capabilities: {', '.join(missing)}",
                        )
                    )
                    continue

                # Candidate passed all hard constraints
                evaluations.append(
                    CandidateEvaluationRecord(
                        provider_id=provider.provider_id,
                        model_id=cap.model_id,
                        is_eligible=True,
                        reason="Passed all hard constraints and capabilities checks.",
                    )
                )
                eligible_candidates.append((provider, cap))

        # Sort eligible candidates based on Profile
        sorted_candidates = self._rank_candidates(eligible_candidates, request, profile)

        chain = [(p, cap.model_id) for p, cap in sorted_candidates]
        return chain, evaluations

    def _rank_candidates(
        self,
        candidates: List[Tuple[AbstractLLMProvider, ModelCapability]],
        request: LLMRequest,
        profile: RoutingProfile,
    ) -> List[Tuple[AbstractLLMProvider, ModelCapability]]:
        """Applies soft preferences and deterministic tie-breaking to sort eligible candidates."""

        def scoring_key(item: Tuple[AbstractLLMProvider, ModelCapability]) -> Tuple[float, str, str]:
            provider, cap = item
            avg_lat = self.metrics_tracker.get_average_latency(provider.provider_id, cap.model_id)

            score = 0.0

            # Preferred provider & explicit model_id bonus
            if request.preferred_provider and request.preferred_provider.lower() == provider.provider_id.lower():
                score -= 2000.0

            if request.model_id and request.model_id.lower() == cap.model_id.lower():
                score -= 1000.0

            if profile == RoutingProfile.PRIVACY_FIRST:
                if provider.is_local:
                    score -= 500.0

            elif profile == RoutingProfile.LATENCY_FIRST:
                score += avg_lat * 10.0

            elif profile == RoutingProfile.COST_AWARE:
                if provider.is_local:
                    score -= 200.0  # Local inference has zero API token cost

            elif profile == RoutingProfile.QUALITY_PREFERRED:
                # Higher context capacity preferred
                score -= cap.context_window / 1000.0

            elif profile == RoutingProfile.BALANCED:
                if provider.is_local:
                    score -= 50.0
                score += avg_lat * 5.0

            # Deterministic tie-breaker (score, provider_id, model_id)
            return (score, provider.provider_id, cap.model_id)

        return sorted(candidates, key=scoring_key)
