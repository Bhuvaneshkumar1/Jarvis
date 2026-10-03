"""
Unit Tests for TaskClassifier (Batch 24).
"""

from jarvis.llm.contracts import LLMRequest, ChatMessage, TaskCategory
from jarvis.core.enums import MessageRole
from jarvis.llm.routing.classifier import TaskClassifier


def test_explicit_task_category():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
        task_category=TaskCategory.CODING,
    )
    assert TaskClassifier.classify(req) == TaskCategory.CODING


def test_metadata_task_category():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
        metadata={"task_category": "REASONING"},
    )
    assert TaskClassifier.classify(req) == TaskCategory.REASONING


def test_tool_planning_classification():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Run a tool")],
        tools=[{"name": "test_tool"}],
    )
    assert TaskClassifier.classify(req) == TaskCategory.TOOL_PLANNING


def test_structured_output_classification():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Get JSON")],
        response_format={"type": "json_object"},
    )
    assert TaskClassifier.classify(req) == TaskCategory.STRUCTURED_OUTPUT


def test_coding_heuristics():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="def process_data(): return True")],
    )
    assert TaskClassifier.classify(req) == TaskCategory.CODING


def test_simple_chat_heuristics():
    req = LLMRequest(
        model_id="test-model",
        messages=[ChatMessage(role=MessageRole.USER, content="Hi there!")],
    )
    assert TaskClassifier.classify(req) == TaskCategory.SIMPLE_CHAT
