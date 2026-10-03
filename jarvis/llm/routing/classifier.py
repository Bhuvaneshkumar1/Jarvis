"""
Task Classifier Subsystem for JARVIS LLM Router (Batch 24).

Classifies LLM requests into standardized TaskCategory buckets using explicit metadata precedence
followed by fast, deterministic prompt and payload heuristics.
"""

import re
import logging
from jarvis.llm.contracts import LLMRequest, TaskCategory

logger = logging.getLogger(__name__)

CODING_PATTERNS = [
    re.compile(r"\b(def|class|import|function|code|refactor|script|sql|python|javascript|typescript|c\+\+|java)\b", re.IGNORECASE),
    re.compile(r"```[a-zA-Z0-9_-]*\n", re.IGNORECASE),
]

DEBUGGING_PATTERNS = [
    re.compile(r"\b(traceback|stack trace|exception|error|bug|fix|crash|issue|failed|debug)\b", re.IGNORECASE),
]

REASONING_PATTERNS = [
    re.compile(r"\b(prove|step by step|logical|why|explain reasoning|derive|math|puzzle|deduce)\b", re.IGNORECASE),
]

SUMMARIZATION_PATTERNS = [
    re.compile(r"\b(summarize|summary|tl;dr|digest|abstract|key points|bullet points)\b", re.IGNORECASE),
]

RESEARCH_PATTERNS = [
    re.compile(r"\b(research|investigate|synthesize|overview|literature|compare and contrast)\b", re.IGNORECASE),
]


class TaskClassifier:
    """Classifies incoming LLM requests into TaskCategory enums."""

    @staticmethod
    def classify(request: LLMRequest) -> TaskCategory:
        """
        Classifies an LLMRequest.
        1. Explicit request.task_category field.
        2. Explicit request.metadata["task_category"] value.
        3. Structural request payloads (tools -> TOOL_PLANNING, response_format -> STRUCTURED_OUTPUT).
        4. Deterministic prompt heuristics.
        5. Default: GENERAL.
        """
        # 1. Explicit request field
        if request.task_category is not None:
            return request.task_category

        # 2. Metadata field
        meta_cat = request.metadata.get("task_category")
        if meta_cat:
            try:
                return TaskCategory(str(meta_cat).upper())
            except ValueError:
                logger.warning(f"Invalid task_category in metadata: '{meta_cat}'. Falling back to heuristics.")

        # 3. Structural payload features
        if request.tools and len(request.tools) > 0:
            return TaskCategory.TOOL_PLANNING

        if request.response_format and request.response_format.get("type") == "json_object":
            return TaskCategory.STRUCTURED_OUTPUT

        # 4. Prompt heuristic matching
        if not request.messages:
            return TaskCategory.GENERAL

        combined_text = " ".join([m.content for m in request.messages]).strip()
        if request.system_instructions:
            combined_text = f"{request.system_instructions} {combined_text}"

        if not combined_text:
            return TaskCategory.SIMPLE_CHAT

        # Check Debugging
        if any(p.search(combined_text) for p in DEBUGGING_PATTERNS):
            return TaskCategory.DEBUGGING

        # Check Coding
        if any(p.search(combined_text) for p in CODING_PATTERNS):
            return TaskCategory.CODING

        # Check Reasoning
        if any(p.search(combined_text) for p in REASONING_PATTERNS):
            return TaskCategory.REASONING

        # Check Summarization
        if any(p.search(combined_text) for p in SUMMARIZATION_PATTERNS):
            return TaskCategory.SUMMARIZATION

        # Check Research
        if any(p.search(combined_text) for p in RESEARCH_PATTERNS):
            return TaskCategory.RESEARCH

        # Short conversational requests
        if len(combined_text) < 100:
            return TaskCategory.SIMPLE_CHAT

        return TaskCategory.GENERAL
