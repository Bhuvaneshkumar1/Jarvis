import pytest
from pydantic import ValidationError
from jarvis.core.contracts.tools import ToolRequestContract, ToolResultContract
from jarvis.core.enums import ToolResultStatus, VerificationResultStatus

def test_tool_contracts_serialization():
    req = ToolRequestContract(
        task_id="task-001",
        tool_name="read_file",
        arguments={"path": "d:/jarvis_v2/pyproject.toml"},
    )
    assert req.call_id.startswith("call-")

    res = ToolResultContract(
        call_id=req.call_id,
        status=ToolResultStatus.SUCCESS,
        output="[file_content]",
        execution_time=0.015,
        verification_state=VerificationResultStatus.PASSED,
    )
    dumped = res.model_dump()
    reconstructed = ToolResultContract.model_validate(dumped)
    assert reconstructed.execution_time == 0.015

def test_tool_result_immutability():
    res = ToolResultContract(call_id="call-123", status=ToolResultStatus.SUCCESS)
    with pytest.raises(ValidationError):
        res.status = ToolResultStatus.FAILED  # Frozen Pydantic model
