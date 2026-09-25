import pytest
from pydantic import ValidationError
from jarvis.core.contracts import (
    TaskContract,
    TaskStepContract,
    AgentContextContract,
    ToolRequestContract,
    ToolResultContract,
    MemoryQueryContract,
    LLMRequestContract,
    ChatMessage,
    PolicyDecisionContract,
    VerificationContract,
    AuditEventContract,
    HealthStatusContract,
)
from jarvis.core.enums import MessageRole

def test_negative_invalid_task_id():
    with pytest.raises(ValidationError):
        TaskContract(task_id="", description="Sample task")

def test_negative_invalid_step_sequence():
    with pytest.raises(ValidationError):
        TaskStepContract(task_id="task-1", sequence=0, description="Invalid sequence")

def test_negative_invalid_agent_context_id():
    with pytest.raises(ValidationError):
        AgentContextContract(agent_id="  ", task_id="task-1", role="Worker")

def test_negative_invalid_tool_request():
    with pytest.raises(ValidationError):
        ToolRequestContract(call_id="call-1", task_id="task-1", tool_name="")

def test_negative_invalid_tool_result_execution_time():
    with pytest.raises(ValidationError):
        ToolResultContract(call_id="call-1", execution_time=-1.5)

def test_negative_invalid_memory_query_threshold():
    with pytest.raises(ValidationError):
        MemoryQueryContract(query="test", relevance_threshold=1.5)

def test_negative_invalid_llm_request_temperature():
    msg = ChatMessage(role=MessageRole.USER, content="Hello")
    with pytest.raises(ValidationError):
        LLMRequestContract(model="llama", messages=[msg], temperature=3.0)

def test_negative_invalid_policy_decision():
    with pytest.raises(ValidationError):
        PolicyDecisionContract(action="", reason="")

def test_negative_invalid_verification_states():
    with pytest.raises(ValidationError):
        VerificationContract(task_id="task-1", expected_state="", observed_state="done")

def test_negative_invalid_audit_event_component():
    with pytest.raises(ValidationError):
        AuditEventContract(component="", action="action")

def test_negative_invalid_health_status_latency():
    with pytest.raises(ValidationError):
        HealthStatusContract(component="DB", latency=-0.5)
