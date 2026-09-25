import os
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.verification import VerificationEngine

def test_orchestrator_pipeline_success(temp_dir):
    orchestrator = Orchestrator()
    target_file = os.path.join(temp_dir, "output.txt")

    def execution_handler(plan, rollback_mgr):
        rollback_mgr.register_file_creation(target_file)
        with open(target_file, "w") as f:
            f.write("Pipeline test output")
        return target_file

    def verifier(output_path):
        return VerificationEngine.verify_file_created(output_path, min_bytes=5)

    result = orchestrator.process_request(
        request_text="Create report output file",
        user_approved=True,
        execution_handler=execution_handler,
        postcondition_verifier=verifier,
    )

    assert result["status"] == "COMPLETED"
    assert result["verification_state"] == "VERIFIED"
    assert os.path.exists(target_file)
