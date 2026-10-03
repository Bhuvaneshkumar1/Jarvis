"""
Capability Matcher Subsystem for JARVIS LLM Router (Batch 24).

Validates model and provider capabilities against LLMRequest requirements, including streaming,
structured JSON output, tool calling, context window capacity, and custom capability tokens.
"""

import logging
from typing import Tuple, List
from jarvis.llm.contracts import LLMRequest, ModelCapability

logger = logging.getLogger(__name__)


class CapabilityMatcher:
    """Evaluates whether a ModelCapability profile satisfies an LLMRequest."""

    @staticmethod
    def estimate_prompt_tokens(request: LLMRequest) -> int:
        """Estimates total prompt token count using conservative character count heuristic (4 chars per token)."""
        char_count = sum(len(m.content) for m in request.messages)
        if request.system_instructions:
            char_count += len(request.system_instructions)
        # 1 token approx 4 characters + 20% overhead
        return int((char_count / 4.0) * 1.2) + 16

    @classmethod
    def evaluate_capability(cls, capability: ModelCapability, request: LLMRequest) -> Tuple[bool, List[str]]:
        """
        Evaluates a ModelCapability against a request's hard requirements.
        Returns (is_capable: bool, missing_reasons: List[str]).
        """
        missing: List[str] = []

        # 1. Text Generation Capability
        if not capability.supports_text_generation:
            missing.append("does_not_support_text_generation")

        # 2. Streaming Capability
        if request.stream and not capability.supports_streaming:
            missing.append("streaming_unsupported")

        # 3. Structured JSON Output Capability
        if request.response_format and request.response_format.get("type") == "json_object":
            if not capability.supports_structured_output:
                missing.append("structured_json_unsupported")

        # 4. Tool / Function Calling Capability
        if request.tools and len(request.tools) > 0:
            if not capability.supports_tool_calling:
                missing.append("tool_calling_unsupported")

        # 5. Context Window Capacity
        est_tokens = cls.estimate_prompt_tokens(request)
        requested_output = request.max_tokens or 512
        total_tokens_needed = est_tokens + requested_output
        if total_tokens_needed > capability.context_window:
            missing.append(f"context_length_exceeded (needed={total_tokens_needed}, capacity={capability.context_window})")

        # 6. Explicit Required Capabilities List
        for req_cap in request.required_capabilities:
            cap_lower = req_cap.lower().strip()
            if cap_lower in ("vision", "image") and not capability.supports_vision:
                missing.append("vision_unsupported")
            elif cap_lower == "reasoning" and not capability.supports_reasoning:
                missing.append("reasoning_unsupported")
            elif cap_lower == "embeddings" and not capability.supports_embeddings:
                missing.append("embeddings_unsupported")

        is_capable = len(missing) == 0
        return is_capable, missing
