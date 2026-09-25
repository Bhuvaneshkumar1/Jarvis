import os
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.verification import PostconditionResult

def test_negative_policy_denial():
    orchestrator = Orchestrator()
    # Requesting deletion without approval
    res = orchestrator.process_request(request_text="Modify system files", user_approved=False)
    # Default settings require approval for modify when user_approved is False
    assert res["status"] == "DENIED"
    assert res["requires_approval"] is True

def test_negative_execution_failure_triggers_rollback(temp_dir):
    orchestrator = Orchestrator()
    created_file = os.path.join(temp_dir, "temp_created.txt")

    def failing_execution(plan, rollback_mgr):
        rollback_mgr.register_file_creation(created_file)
        with open(created_file, "w") as f:
            f.write("Partially written data")
        raise RuntimeError("Simulated crash during tool execution!")

    res = orchestrator.process_request(
        request_text="Perform heavy operation",
        user_approved=True,
        execution_handler=failing_execution,
    )

    assert res["status"] == "FAILED"
    assert res["verification_state"] == "ROLLED_BACK"
    assert "Simulated crash" in res["error"]
    # Verify rollback cleaned up created file
    assert not os.path.exists(created_file)

def test_negative_postcondition_verification_failure(temp_dir):
    orchestrator = Orchestrator()

    def bad_execution(plan, rollback_mgr):
        return "Not expected path"

    def failing_verifier(output):
        return PostconditionResult(passed=False, reason="Output checksum mismatch.")

    res = orchestrator.process_request(
        request_text="Generate report",
        user_approved=True,
        execution_handler=bad_execution,
        postcondition_verifier=failing_verifier,
    )

    assert res["status"] == "FAILED"
    assert res["verification_state"] == "ROLLED_BACK"
    assert "Postcondition verification failed" in res["error"]
