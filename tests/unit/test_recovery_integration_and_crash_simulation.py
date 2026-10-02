"""
Crash & Restart Simulation and Runtime Integration Tests for State Recovery (Batch 19).
"""

import pytest
import time
from config.settings import Settings
from jarvis.core.enums import TaskStatus, RuntimeState
from jarvis.core.runtime.application import JarvisApplication
from jarvis.core.tasks.manager import TaskManager
from jarvis.core.tasks.repository import TaskRepository
from jarvis.security.policy.models import ApprovalRequest, ApprovalStatus

from jarvis.security.policy.store import PolicyRepository
from jarvis.core.exceptions import RecoveryIntegrityError


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_recovery_crash_sim.db")


@pytest.mark.asyncio
async def test_jarvis_application_startup_recovery_integration(temp_db_path):
    # Step 1: Populate database with state requiring recovery
    task_repo = TaskRepository(db_path=temp_db_path)
    policy_repo = PolicyRepository(db_path=temp_db_path)

    # Interrupted running task
    task = task_repo.create_task(
        __import__("jarvis.core.tasks.contracts", fromlist=["TaskRecord"]).TaskRecord(
            task_id="t-crash-1",
            title="Interrupted Task",
            status=TaskStatus.RUNNING,
        )
    )

    # Overdue approval
    now = time.time()
    policy_repo.save_approval_request(
        ApprovalRequest(
            approval_id="appr-crash-1",
            principal_id="user-1",
            requested_action="act",
            target_resource="res",
            exact_scope="sc",
            task_id=task.task_id,
            expires_at=now - 50,
        )
    )

    # Step 2: Initialize application kernel with this database
    tm = TaskManager(repository=task_repo, db_path=temp_db_path)
    app = JarvisApplication(
        settings=Settings(),
        task_manager=tm,
    )

    # Start application (runs startup recovery automatically)
    await app.start()

    assert app.state == RuntimeState.RUNNING

    # Verify task was recovered cleanly to INTERRUPTED / BLOCKED
    recovered_task = task_repo.get_task("t-crash-1")
    assert recovered_task.status in (
        TaskStatus.INTERRUPTED,
        TaskStatus.RETRY_PENDING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    )

    # Verify approval was expired
    appr = policy_repo.get_approval_request("appr-crash-1")
    assert appr.status == ApprovalStatus.EXPIRED

    await app.shutdown("Test complete")


def test_fatal_database_integrity_failure_fails_closed(temp_db_path):
    from jarvis.core.recovery.store import RecoveryRepository

    repo = RecoveryRepository(db_path=temp_db_path)

    # Corrupt database file header/content
    with open(temp_db_path, "wb") as f:
        f.write(b"CORRUPTED_NON_SQLITE_DATA_HEADER")

    with pytest.raises(RecoveryIntegrityError, match="Database corrupted"):
        repo.validate_database_integrity()
