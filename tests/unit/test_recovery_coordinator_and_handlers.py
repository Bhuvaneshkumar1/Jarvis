"""
Unit & Integration Tests for Recovery Coordinator and Specialized Handlers (Batch 19).
"""

import pytest
import time
from jarvis.core.enums import TaskStatus
from jarvis.core.tasks.manager import TaskManager
from jarvis.core.tasks.repository import TaskRepository
from jarvis.security.policy.models import ApprovalRequest
from jarvis.security.policy.store import PolicyRepository
from jarvis.core.recovery.models import RecoveryStatus
from jarvis.core.recovery.store import RecoveryRepository
from jarvis.core.recovery.handlers import (
    TaskRecoveryHandler,
    ApprovalRecoveryHandler,
    EventOutboxHandler,
)
from jarvis.core.recovery.coordinator import RecoveryCoordinator


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_recovery_coordinator.db")


def test_task_recovery_handler_classification(temp_db_path):
    task_repo = TaskRepository(db_path=temp_db_path)
    handler = TaskRecoveryHandler(task_repository=task_repo)

    # 1. Normal task in RUNNING -> transitions to INTERRUPTED
    task_repo.create_task(
        __import__("jarvis.core.tasks.contracts", fromlist=["TaskRecord"]).TaskRecord(
            task_id="t-running",
            title="Running task",
            status=TaskStatus.RUNNING,
        )
    )

    # 2. Idempotent task in RUNNING -> transitions to READY
    task_repo.create_task(
        __import__("jarvis.core.tasks.contracts", fromlist=["TaskRecord"]).TaskRecord(
            task_id="t-idempotent",
            title="Idempotent task",
            status=TaskStatus.RUNNING,
            idempotency_key="key-123",
        )
    )

    # 3. Task with side-effects in RUNNING -> requires manual intervention / BLOCKED
    task_repo.create_task(
        __import__("jarvis.core.tasks.contracts", fromlist=["TaskRecord"]).TaskRecord(
            task_id="t-sideeffect",
            title="Side effect task",
            status=TaskStatus.RUNNING,
            metadata={"has_external_side_effects": True},
        )
    )

    summary = handler.recover_tasks()
    assert summary["inspected_count"] == 3
    assert summary["recovered_count"] == 2
    assert summary["manual_intervention_count"] == 1

    assert task_repo.get_task("t-running").status == TaskStatus.INTERRUPTED
    assert task_repo.get_task("t-idempotent").status == TaskStatus.READY
    assert task_repo.get_task("t-sideeffect").status == TaskStatus.INTERRUPTED


def test_approval_recovery_handler(temp_db_path):
    policy_repo = PolicyRepository(db_path=temp_db_path)
    task_mgr = TaskManager(db_path=temp_db_path)
    handler = ApprovalRecoveryHandler(policy_repository=policy_repo, task_manager=task_mgr)

    # Create task needing approval
    t = task_mgr.create_task(title="Approval task")
    task_mgr.transition_task(t.task_id, TaskStatus.WAITING_APPROVAL, reason="Wait approval")

    # Create overdue approval
    now = time.time()
    policy_repo.save_approval_request(
        ApprovalRequest(
            approval_id="appr-overdue-1",
            principal_id="user-1",
            requested_action="act",
            target_resource="res",
            exact_scope="sc",
            task_id=t.task_id,
            expires_at=now - 100,
        )
    )

    res = handler.recover_approvals(now=now)
    assert res["inspected_count"] == 1
    assert "appr-overdue-1" in res["expired_approval_ids"]

    # Verify task updated to BLOCKED
    assert task_mgr.get_task(t.task_id).status == TaskStatus.BLOCKED


def test_event_outbox_handler(temp_db_path):
    rec_repo = RecoveryRepository(db_path=temp_db_path)
    rec_repo.enqueue_outbox_event("TaskStarted", {"task_id": "t-1"})

    handler = EventOutboxHandler(recovery_repository=rec_repo)
    res = handler.reconcile_outbox()

    assert res["inspected_count"] == 1


def test_recovery_coordinator_full_sequence(temp_db_path):
    coordinator = RecoveryCoordinator(db_path=temp_db_path)
    rec = coordinator.execute_recovery()

    assert rec.status in (RecoveryStatus.COMPLETED, RecoveryStatus.COMPLETED_WITH_WARNINGS)
    assert rec.started_at > 0
    assert rec.completed_at is not None
    assert rec.completed_at >= rec.started_at
