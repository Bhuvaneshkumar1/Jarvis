"""
Centralized Policy-Aware Intelligent LLM Router for JARVIS AI OS (Batch 24).

Implements centralized request classification, privacy boundary enforcement,
profile-driven candidate ranking, bounded provider fallback, and streaming safety.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional, AsyncIterator

from jarvis.core.enums import HealthState
from jarvis.llm.base import AbstractLLMProvider
from jarvis.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StreamEventType,
    ModelCapability,
    RoutingProfile,
    LLMProviderState,
)
from jarvis.llm.registry import LLMProviderRegistry
from jarvis.llm.exceptions import (
    LLMError,
    ProviderUnavailableError,
)
from jarvis.llm.routing.classifier import TaskClassifier
from jarvis.llm.routing.routing_policy import RoutingPolicyEngine
from jarvis.llm.routing.candidate_selector import CandidateSelector
from jarvis.llm.routing.fallback_manager import FallbackManager
from jarvis.llm.routing.routing_metrics import RoutingMetricsTracker
from jarvis.llm.routing.routing_explainer import RoutingExplainer

logger = logging.getLogger("jarvis.llm.router")


class LLMRouter(AbstractLLMProvider):
    """
    Centralized, Policy-Aware Intelligent LLM Router.
    Routes LLM requests to NVIDIA NIM, OpenRouter, or Local LLM providers based on task category,
    data classification privacy boundaries, capability matching, and fallback policies.
    """

    def __init__(
        self,
        registry: LLMProviderRegistry,
        provider_id: str = "router",
        policy_engine: Optional[RoutingPolicyEngine] = None,
        classifier: Optional[TaskClassifier] = None,
        candidate_selector: Optional[CandidateSelector] = None,
        fallback_manager: Optional[FallbackManager] = None,
        metrics_tracker: Optional[RoutingMetricsTracker] = None,
        default_profile: Optional[RoutingProfile] = None,
        max_attempts: Optional[int] = None,
        allow_fallback: Optional[bool] = None,
    ):
        super().__init__(provider_id=provider_id, is_local=False)

        self.registry = registry
        self.policy_engine = policy_engine or RoutingPolicyEngine()
        self.classifier = classifier or TaskClassifier()
        self.metrics_tracker = metrics_tracker or RoutingMetricsTracker()
        self.candidate_selector = candidate_selector or CandidateSelector(
            registry=self.registry,
            policy_engine=self.policy_engine,
            metrics_tracker=self.metrics_tracker,
        )

        env_profile = os.getenv("LLM_ROUTING_PROFILE", "BALANCED").upper()
        try:
            self.default_profile = default_profile or RoutingProfile(env_profile)
        except ValueError:
            self.default_profile = RoutingProfile.BALANCED

        max_att = max_attempts or int(os.getenv("LLM_ROUTING_MAX_ATTEMPTS", "3"))
        fallback_enabled = allow_fallback if allow_fallback is not None else os.getenv("LLM_ROUTING_ALLOW_FALLBACK", "true").lower() in ("true", "1", "yes")

        self.fallback_manager = fallback_manager or FallbackManager(
            max_attempts=max_att,
            allow_fallback=fallback_enabled,
        )

    async def initialize(self) -> None:
        """Initializes router state."""
        self.state = LLMProviderState.READY
        logger.info(f"LLMRouter initialized (default_profile={self.default_profile.value}, max_attempts={self.fallback_manager.max_attempts}).")

    async def close(self) -> None:
        """Closes router resources."""
        self.state = LLMProviderState.CLOSED
        logger.info("LLMRouter closed.")

    async def health_check(self) -> HealthState:
        """Checks overall subsystem health across registered providers."""
        providers = self.registry.list_providers()
        if not providers:
            return HealthState.UNHEALTHY

        healthy_count = 0
        for p in providers:
            if p.state in (LLMProviderState.READY, LLMProviderState.DEGRADED):
                healthy_count += 1

        if healthy_count > 0:
            return HealthState.HEALTHY
        return HealthState.UNHEALTHY

    async def list_models(self) -> List[ModelCapability]:
        """Lists aggregated model capabilities across all registered providers."""
        all_models: List[ModelCapability] = []
        for p in self.registry.list_providers():
            try:
                models = await p.list_models()
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"Error listing models for provider '{p.provider_id}': {e}")
        return all_models

    async def get_capabilities(self, model_id: str) -> ModelCapability:
        """Finds capabilities for a model ID across registered providers."""
        models = await self.list_models()
        for cap in models:
            if cap.model_id == model_id:
                return cap

        return ModelCapability(
            model_id=model_id,
            provider_id=self.provider_id,
            supports_text_generation=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_tool_calling=True,
            context_window=4096,
            max_output_tokens=2048,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Public entrypoint for router generation bypassing single-provider privacy restriction."""
        if self.state not in (LLMProviderState.READY, LLMProviderState.DEGRADED):
            raise ProviderUnavailableError(
                f"Provider '{self.provider_id}' is not in READY state (current: {self.state.value}).",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )
        return await self._do_generate(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Public entrypoint for router streaming bypassing single-provider privacy restriction."""
        if self.state not in (LLMProviderState.READY, LLMProviderState.DEGRADED):
            raise ProviderUnavailableError(
                f"Provider '{self.provider_id}' is not in READY state (current: {self.state.value}).",
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )
        async for event in self._do_stream(request):
            yield event

    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        """Executes intelligent LLM request routing and non-streaming completion with fallback."""
        # 1. Validate request privacy policy
        self.policy_engine.validate_request_policy(request)

        # 2. Task Classification
        task_cat = self.classifier.classify(request)

        # 3. Routing Profile
        profile = request.routing_profile or self.default_profile

        # 4. Candidate Selection
        chain, evaluations = await self.candidate_selector.select_candidates(request, profile)

        if not chain:
            explanation = RoutingExplainer.create_explanation(
                request=request,
                task_category=task_cat,
                profile=profile,
                evaluations=evaluations,
                selected_provider_id=None,
                selected_model_id=None,
                attempts=[],
                outcome="REJECTED_NO_ELIGIBLE_CANDIDATES",
            )
            err_msg = (
                f"No eligible LLM providers satisfy privacy and capability bounds for data classification "
                f"'{request.data_classification.value}'. Explanation: {explanation}"
            )
            raise ProviderUnavailableError(
                err_msg,
                provider_id=self.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )

        attempts_history: List[Dict[str, Any]] = []
        last_exception: Optional[Exception] = None

        # 5. Attempt Execution Loop
        for attempt_idx, (provider, model_id) in enumerate(chain, start=1):
            next_candidate_provider = chain[attempt_idx][0] if attempt_idx < len(chain) else None

            # Build candidate-specific request copy
            cand_request = request.model_copy(update={"model_id": model_id})

            start_t = time.time()
            try:
                logger.info(
                    f"LLMRouter attempt {attempt_idx}/{self.fallback_manager.max_attempts}: "
                    f"dispatching to '{provider.provider_id}' model '{model_id}' (task={task_cat.value})."
                )

                # Execute inference on selected provider
                response = await provider.generate(cand_request)
                latency = time.time() - start_t

                # Record metrics
                self.metrics_tracker.record_success(provider.provider_id, model_id, latency)

                attempts_history.append(
                    {
                        "attempt": attempt_idx,
                        "provider_id": provider.provider_id,
                        "model_id": model_id,
                        "latency": round(latency, 4),
                        "status": "SUCCESS",
                    }
                )

                explanation = RoutingExplainer.create_explanation(
                    request=request,
                    task_category=task_cat,
                    profile=profile,
                    evaluations=evaluations,
                    selected_provider_id=provider.provider_id,
                    selected_model_id=model_id,
                    attempts=attempts_history,
                    outcome="SUCCESS",
                )

                # Attach routing explanation to response metadata
                new_metadata = dict(response.metadata)
                new_metadata["routing_explanation"] = explanation

                return LLMResponse(
                    request_id=response.request_id,
                    provider=response.provider_id,
                    model=response.model_id,
                    content=response.generated_content,
                    finish_reason=response.finish_reason,
                    usage=response.usage,
                    latency=response.latency,
                    structured_output=response.structured_output,
                    tool_calls=response.tool_calls,
                    metadata=new_metadata,
                )

            except Exception as exc:
                latency = time.time() - start_t
                last_exception = exc
                self.metrics_tracker.record_failure(provider.provider_id, model_id, str(exc))

                attempts_history.append(
                    {
                        "attempt": attempt_idx,
                        "provider_id": provider.provider_id,
                        "model_id": model_id,
                        "latency": round(latency, 4),
                        "status": "FAILED",
                        "error": str(exc),
                    }
                )

                can_fb, fb_reason = self.fallback_manager.can_fallback(
                    request=request,
                    current_attempt=attempt_idx,
                    error=exc,
                    next_provider=next_candidate_provider,
                )

                if can_fb:
                    logger.warning(f"LLMRouter attempt {attempt_idx} failed on '{provider.provider_id}': {exc}. Falling back: {fb_reason}")
                    continue
                else:
                    logger.error(f"LLMRouter attempt {attempt_idx} failed on '{provider.provider_id}': {exc}. Fallback denied: {fb_reason}")
                    explanation = RoutingExplainer.create_explanation(
                        request=request,
                        task_category=task_cat,
                        profile=profile,
                        evaluations=evaluations,
                        selected_provider_id=provider.provider_id,
                        selected_model_id=model_id,
                        attempts=attempts_history,
                        outcome="FAILED",
                    )
                    if hasattr(exc, "metadata") and isinstance(getattr(exc, "metadata"), dict):
                        exc.metadata["routing_explanation"] = explanation
                    raise exc

        # All attempts exhausted
        if last_exception:
            raise last_exception
        raise ProviderUnavailableError("All candidate LLM providers failed execution.", provider_id=self.provider_id)

    async def _do_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Executes intelligent LLM request routing and streaming completion with safe pre-chunk fallback."""
        self.policy_engine.validate_request_policy(request)
        task_cat = self.classifier.classify(request)
        profile = request.routing_profile or self.default_profile

        chain, evaluations = await self.candidate_selector.select_candidates(request, profile)

        if not chain:
            yield LLMStreamEvent(
                request_id=request.request_id,
                event_type=StreamEventType.STREAM_FAILED,
                error_message=f"No eligible LLM providers satisfy privacy and capability bounds for data classification '{request.data_classification.value}'.",
            )
            return

        for attempt_idx, (provider, model_id) in enumerate(chain, start=1):
            logger.info(
                f"LLMRouter stream attempt {attempt_idx}/{self.fallback_manager.max_attempts}: "
                f"dispatching to '{provider.provider_id}' model '{model_id}' (task={task_cat.value})."
            )
            next_candidate_provider = chain[attempt_idx][0] if attempt_idx < len(chain) else None
            cand_request = request.model_copy(update={"model_id": model_id})

            has_emitted_delta = False
            start_t = time.time()

            try:
                async for event in provider.stream(cand_request):
                    if event.event_type == StreamEventType.TEXT_DELTA and event.text_delta:
                        has_emitted_delta = True

                    if event.event_type == StreamEventType.STREAM_FAILED:
                        if has_emitted_delta:
                            # CRITICAL: Post-chunk stream failure -> DO NOT SWITCH PROVIDERS!
                            yield event
                            return
                        else:
                            raise LLMError(event.error_message or "Stream initialization failure")

                    yield event

                latency = time.time() - start_t
                self.metrics_tracker.record_success(provider.provider_id, model_id, latency)
                return

            except Exception as exc:
                latency = time.time() - start_t
                self.metrics_tracker.record_failure(provider.provider_id, model_id, str(exc))

                if has_emitted_delta:
                    # Never switch providers after partial user-visible text chunk has been emitted
                    yield LLMStreamEvent(
                        request_id=request.request_id,
                        event_type=StreamEventType.STREAM_FAILED,
                        error_message=f"Stream interrupted during output generation: {exc}",
                    )
                    return

                can_fb, fb_reason = self.fallback_manager.can_fallback(
                    request=request,
                    current_attempt=attempt_idx,
                    error=exc,
                    next_provider=next_candidate_provider,
                )

                if can_fb:
                    logger.warning(f"LLMRouter stream attempt {attempt_idx} failed on '{provider.provider_id}': {exc}. Falling back to next candidate.")
                    continue
                else:
                    yield LLMStreamEvent(
                        request_id=request.request_id,
                        event_type=StreamEventType.STREAM_FAILED,
                        error_message=f"Streaming failed: {exc}",
                    )
                    return
