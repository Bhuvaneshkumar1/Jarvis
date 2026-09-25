import os
from jarvis.core.tool_registry import ToolRegistry
from jarvis.core.policy import ActionType, RiskLevel
from jarvis.core.verification import VerificationEngine


def test_tool_registration_and_execution(temp_dir):
    registry = ToolRegistry()

    def dummy_handler(target: str, data: str):
        filepath = os.path.join(temp_dir, target)
        with open(filepath, "w") as f:
            f.write(data)
        return filepath

    registry.register_tool(
        name="create_file",
        description="Creates a file",
        action_type=ActionType.CREATE,
        handler=dummy_handler,
        risk_level=RiskLevel.LOW,
    )

    def verify_fn(filepath):
        return VerificationEngine.verify_file_created(filepath, min_bytes=1)

    result = registry.execute_tool(
        name="create_file",
        kwargs={"target": "test_doc.txt", "data": "Sample Content"},
        postcondition_verifier=verify_fn,
    )

    assert result.success is True
    assert result.verified is True
    assert result.policy_allowed is True
    assert os.path.exists(result.output)
