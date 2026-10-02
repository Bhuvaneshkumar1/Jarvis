"""
Database Integration & Persistence Tests for Approval Subsystem (Batch 18).
"""

import os
import time
import pytest
from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
    PrincipalType,
)
from jarvis.security.policy.store import PolicyRepository
from jarvis.security.policy.exceptions import (
    ApprovalNotFoundError,
    StaleApprovalVersionError,
    ApprovalAlreadyConsumedError,
)


@pytest.fixture
def temp_db_path(tmp_path):
    db_file = tmp_path / "test_approval_persistence.db"
    return str(db_file)


@pytest.fixture
def repo(temp_db_path):
    return PolicyRepository(db_path=temp_db_path)


def test_migration_and_approval_save_retrieve(repo):
    req = ApprovalRequest(
        approval_id="appr-test001",
        principal_id="user-123",
        principal_type=PrincipalType.USER,
        requested_action="file.write",
        target_resource="/data/test.txt",
        exact_scope="write_scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Test approval request",
        task_id="task-001",
        expires_at=time.time() + 3600,
        request_fingerprint="fp-testfingerprint",
    )

    saved = repo.save_approval_request(req)
    assert saved.approval_id == "appr-test001"
    assert saved.version == 1

    retrieved = repo.get_approval_request("appr-test001")
    assert retrieved is not None
    assert retrieved.approval_id == "appr-test001"
    assert retrieved.principal_id == "user-123"
    assert retrieved.requested_action == "file.write"
    assert retrieved.status == ApprovalStatus.PENDING
    assert retrieved.request_fingerprint == "fp-testfingerprint"


def test_approval_queries(repo):
    now = time.time()
    req1 = ApprovalRequest(
        approval_id="appr-001",
        principal_id="user-A",
        requested_action="act1",
        target_resource="res1",
        exact_scope="scope1",
        task_id="task-X",
        expires_at=now + 100,
        created_at=now - 50,
    )
    req2 = ApprovalRequest(
        approval_id="appr-002",
        principal_id="user-A",
        requested_action="act2",
        target_resource="res2",
        exact_scope="scope2",
        task_id="task-Y",
        expires_at=now + 200,
        created_at=now - 20,
    )
    repo.save_approval_request(req1)
    repo.save_approval_request(req2)

    # By Task ID
    task_x_apprs = repo.get_approvals_by_task_id("task-X")
    assert len(task_x_apprs) == 1
    assert task_x_apprs[0].approval_id == "appr-001"

    # By Requester
    user_a_apprs = repo.get_approvals_by_requester("user-A")
    assert len(user_a_apprs) == 2

    # By Status
    pending = repo.list_pending_approvals()
    assert len(pending) == 2

    # Time range
    time_range_apprs = repo.list_approvals_in_time_range(now - 60, now)
    assert len(time_range_apprs) == 2


def test_optimistic_locking_and_status_update(repo):
    now = time.time()
    req = ApprovalRequest(
        approval_id="appr-opt01",
        principal_id="user-1",
        requested_action="act",
        target_resource="res",
        exact_scope="sc",
        expires_at=now + 3600,
    )
    repo.save_approval_request(req)

    # Update with correct version
    updated = repo.update_approval_status(
        approval_id="appr-opt01",
        new_status=ApprovalStatus.APPROVED,
        approver_id="user-approver",
        reason="Approved for testing",
        expected_version=1,
    )
    assert updated.status == ApprovalStatus.APPROVED
    assert updated.version == 2
    assert updated.approver_id == "user-approver"

    # Stale version update fails
    with pytest.raises(StaleApprovalVersionError):
        repo.update_approval_status(
            approval_id="appr-opt01",
            new_status=ApprovalStatus.REJECTED,
            approver_id="user-other",
            expected_version=1,  # Version is now 2
        )


def test_atomic_consumption(repo):
    now = time.time()
    req = ApprovalRequest(
        approval_id="appr-consume",
        principal_id="user-1",
        requested_action="act",
        target_resource="res",
        exact_scope="sc",
        expires_at=now + 3600,
    )
    repo.save_approval_request(req)
    repo.update_approval_status("appr-consume", ApprovalStatus.APPROVED, approver_id="admin")

    # Consume
    consumed = repo.consume_approval_atomically("appr-consume", consumer_task_id="task-c1")
    assert consumed.status == ApprovalStatus.CONSUMED
    assert consumed.consumed_by_task_id == "task-c1"

    # Re-consume fails
    with pytest.raises(ApprovalAlreadyConsumedError):
        repo.consume_approval_atomically("appr-consume", consumer_task_id="task-c2")
