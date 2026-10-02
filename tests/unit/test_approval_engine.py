"""
Unit & Integration Tests for Persistent Approval Engine & Scoped Approvals (Batch 15).
"""

import os
import pytest
import time
import tempfile
from jarvis.security.policy import (
    PolicyRepository,
    ApprovalEngine,
    PolicyEngine,
    AuthorizationRequest,
    Principal,
    PrincipalType,
    RiskLevel,
    ApprovalStatus,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    AuthorizationDeniedError,
)


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_policy.db")
        repo = PolicyRepository(db_path=db_path)
        yield repo


def test_approval_creation_and_retrieval(temp_repo):
    engine = ApprovalEngine(repository=temp_repo)
    appr = engine.create_approval_request(
        principal_id="user_1",
        principal_type=PrincipalType.USER,
        action="filesystem.delete",
        resource="D:\\Projects\\app.py",
        scope="task_123",
        risk_level=RiskLevel.HIGH,
        reason="Clean up temp build file",
        task_id="task_123",
    )

    assert appr.approval_id.startswith("appr-")
    assert appr.status == ApprovalStatus.PENDING

    fetched = engine.get_approval(appr.approval_id)
    assert fetched is not None
    assert fetched.approval_id == appr.approval_id
    assert fetched.requested_action == "filesystem.delete"


def test_approval_lifecycle_and_agent_self_approval_prevention(temp_repo):
    engine = ApprovalEngine(repository=temp_repo)
    appr = engine.create_approval_request(
        principal_id="agent_1",
        principal_type=PrincipalType.AGENT,
        action="filesystem.delete",
        resource="D:\\file.txt",
        scope="scope",
        risk_level=RiskLevel.HIGH,
        reason="Agent delete request",
    )

    agent_principal = Principal(principal_id="agent_1", principal_type=PrincipalType.AGENT, permissions=["*"])

    # Agent self-approval attempt MUST FAIL
    with pytest.raises(AuthorizationDeniedError):
        engine.approve_request(appr.approval_id, approver_principal=agent_principal)

    # Valid user approval MUST SUCCEED
    user_principal = Principal(principal_id="user_admin", principal_type=PrincipalType.USER, permissions=["*"])
    approved = engine.approve_request(appr.approval_id, approver_principal=user_principal)
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approver_id == "user_admin"


def test_atomic_single_use_approval_consumption_and_replay_protection(temp_repo):
    appr_engine = ApprovalEngine(repository=temp_repo)
    policy_engine = PolicyEngine(approval_engine=appr_engine)

    # Create & approve request
    appr = appr_engine.create_approval_request(
        principal_id="user_1",
        principal_type=PrincipalType.USER,
        action="filesystem.delete",
        resource="D:\\Projects\\file.txt",
        scope="scope",
        risk_level=RiskLevel.HIGH,
        reason="Delete file",
        task_id="task_999",
    )
    user_principal = Principal(principal_id="user_1", principal_type=PrincipalType.USER, permissions=["filesystem.delete"])
    appr_engine.approve_request(appr.approval_id, approver_principal=user_principal)

    auth_req = AuthorizationRequest(
        principal=user_principal,
        action="filesystem.delete",
        resource="D:\\Projects\\file.txt",
        task_id="task_999",
        approval_id=appr.approval_id,
        user_approved=True,
    )

    # First consumption MUST SUCCEED with TOCTOU policy evaluation
    consumed = appr_engine.consume_approval(
        appr.approval_id,
        request=auth_req,
        policy_evaluator_fn=policy_engine.evaluate,
    )
    assert consumed.status == ApprovalStatus.CONSUMED

    # Replay attempt MUST FAIL
    with pytest.raises(ApprovalAlreadyConsumedError):
        appr_engine.consume_approval(appr.approval_id, request=auth_req)


def test_approval_expiration_and_expired_reuse_prevention(temp_repo):
    engine = ApprovalEngine(repository=temp_repo)
    appr = engine.create_approval_request(
        principal_id="user_1",
        principal_type=PrincipalType.USER,
        action="filesystem.modify",
        resource="D:\\file.txt",
        scope="scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Modify file",
        expiration_seconds=0.01,  # Expires immediately
    )
    time.sleep(0.05)

    user_principal = Principal(principal_id="user_1", principal_type=PrincipalType.USER, permissions=["*"])

    # Attempting to approve expired request MUST FAIL
    with pytest.raises(ApprovalExpiredError):
        engine.approve_request(appr.approval_id, approver_principal=user_principal)


def test_scoped_approval_lifecycle_and_path_boundary_enforcement(temp_repo):
    appr_engine = ApprovalEngine(repository=temp_repo)
    policy_engine = PolicyEngine(approval_engine=appr_engine)

    # Create scoped approval for D:\Projects\ExampleApp
    appr_engine.create_scoped_approval(
        principal_id="agent_coder",
        allowed_actions=["filesystem.modify", "code.modify"],
        allowed_resources=["D:\\Projects\\ExampleApp"],
        max_risk_level=RiskLevel.MEDIUM,
        duration_seconds=3600.0,
    )

    p = Principal(principal_id="agent_coder", principal_type=PrincipalType.AGENT, permissions=["filesystem.modify", "code.modify"])

    # Modification INSIDE project scope -> ALLOWED
    req_inside = AuthorizationRequest(
        principal=p,
        action="filesystem.modify",
        resource="D:\\Projects\\ExampleApp\\src\\index.ts",
    )
    dec_inside = policy_engine.evaluate(req_inside)
    assert dec_inside.allowed

    # Modification OUTSIDE project scope -> REQUIRES APPROVAL / DENIED
    req_outside = AuthorizationRequest(
        principal=p,
        action="filesystem.modify",
        resource="D:\\Projects\\OtherApp\\secret.env",
    )
    dec_outside = policy_engine.evaluate(req_outside)
    assert not dec_outside.allowed or dec_outside.requires_user_approval


def test_approval_persistence_across_restart():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "restart_test.db")

        # Session 1: Create approval & save to disk
        repo1 = PolicyRepository(db_path=db_path)
        engine1 = ApprovalEngine(repository=repo1)
        created = engine1.create_approval_request(
            principal_id="user_1",
            principal_type=PrincipalType.USER,
            action="git.commit",
            resource="D:\\repo",
            scope="task_1",
            risk_level=RiskLevel.HIGH,
            reason="Commit changes",
        )
        user_p = Principal(principal_id="user_1", principal_type=PrincipalType.USER, permissions=["*"])
        engine1.approve_request(created.approval_id, approver_principal=user_p)

        # Session 2: Simulate restart by instantiating new repo & engine instance pointing to same db
        repo2 = PolicyRepository(db_path=db_path)
        engine2 = ApprovalEngine(repository=repo2)

        fetched = engine2.get_approval(created.approval_id)
        assert fetched is not None
        assert fetched.status == ApprovalStatus.APPROVED
        assert fetched.requested_action == "git.commit"
