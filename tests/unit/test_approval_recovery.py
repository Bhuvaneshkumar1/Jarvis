"""
Restart Recovery & Task Synchronization Unit Tests for Approval Subsystem (Batch 18).
"""

import time
import pytest
from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    Principal,
    PrincipalType,
    RiskLevel,
)
from jarvis.security.policy.store import PolicyRepository
from jarvis.security.policy.approval import ApprovalEngine
from jarvis.security.policy.recovery import ApprovalRecoveryService
from jarvis.core.tasks.manager import TaskManager
from jarvis.core.enums import TaskStatus


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_approval_recovery.db")


def test_approval_state_persists_across_restart(temp_db_path):
    # Step 1: Initialize database and save records
    repo1 = PolicyRepository(db_path=temp_db_path)
    engine1 = ApprovalEngine(repository=repo1)

    req1 = engine1.create_approval_request(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        action="act1",
        resource="res1",
        scope="sc1",
        risk_level=RiskLevel.LOW,
        reason="Pending request",
    )
    req2 = engine1.create_approval_request(
        principal_id="user-2",
        principal_type=PrincipalType.USER,
        action="act2",
        resource="res2",
        scope="sc2",
        risk_level=RiskLevel.MEDIUM,
        reason="Approved request",
    )

    admin = Principal(principal_id="admin-1", principal_type=PrincipalType.USER)
    engine1.approve_request(req2.approval_id, admin, session_valid=True)

    # Step 2: "Simulate Restart" by destroying references and instantiating fresh repo & engine
    del repo1
    del engine1

    repo2 = PolicyRepository(db_path=temp_db_path)
    engine2 = ApprovalEngine(repository=repo2)

    appr1 = engine2.get_approval(req1.approval_id)
    appr2 = engine2.get_approval(req2.approval_id)

    assert appr1 is not None
    assert appr1.status == ApprovalStatus.PENDING

    assert appr2 is not None
    assert appr2.status == ApprovalStatus.APPROVED


def test_overdue_approval_expiry_recovery(temp_db_path):
    repo = PolicyRepository(db_path=temp_db_path)
    task_mgr = TaskManager(db_path=temp_db_path)

    # Create task
    task = task_mgr.create_task(title="Approval task")
    task_mgr.transition_task(task.task_id, TaskStatus.WAITING_APPROVAL, reason="Waiting user approval")

    # Create overdue approval request (expires in past)
    now = time.time()
    repo.save_approval_request(
        ApprovalRequest(
            approval_id="appr-overdue",
            principal_id="user-1",
            requested_action="act",
            target_resource="res",
            exact_scope="sc",
            task_id=task.task_id,
            expires_at=now - 50,
        )
    )

    recovery = ApprovalRecoveryService(repository=repo, task_manager=task_mgr)
    expired_list = recovery.recover_expired_approvals(now=now)

    assert len(expired_list) == 1
    assert expired_list[0].approval_id == "appr-overdue"
    assert expired_list[0].status == ApprovalStatus.EXPIRED

    # Verify task status updated to BLOCKED
    updated_task = task_mgr.get_task(task.task_id)
    assert updated_task.status == TaskStatus.BLOCKED

    # Idempotency check: running recovery again finds 0 overdue
    second_run = recovery.recover_expired_approvals(now=now)
    assert len(second_run) == 0


def test_task_manager_approval_granted_sync(temp_db_path):
    repo = PolicyRepository(db_path=temp_db_path)
    task_mgr = TaskManager(db_path=temp_db_path)
    engine = ApprovalEngine(repository=repo, task_manager=task_mgr)

    task = task_mgr.create_task(title="Task needing approval")
    task_mgr.transition_task(task.task_id, TaskStatus.WAITING_APPROVAL, reason="Wait approval")

    req = engine.create_approval_request(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        action="act",
        resource="res",
        scope="sc",
        risk_level=RiskLevel.MEDIUM,
        reason="Need approval",
        task_id=task.task_id,
    )

    admin = Principal(principal_id="admin-1", principal_type=PrincipalType.USER)
    engine.approve_request(req.approval_id, admin, session_valid=True)

    updated_task = task_mgr.get_task(task.task_id)
    assert updated_task.status == TaskStatus.READY
