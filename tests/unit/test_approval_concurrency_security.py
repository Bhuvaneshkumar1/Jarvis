"""
Concurrency and Security Unit Tests for Approval Subsystem (Batch 18).
"""

import time
import pytest
import concurrent.futures
from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    Principal,
    PrincipalType,
    RiskLevel,
    AuthorizationRequest,
)
from jarvis.security.policy.store import PolicyRepository
from jarvis.security.policy.approval import ApprovalEngine
from jarvis.security.policy.exceptions import (
    AuthorizationDeniedError,
    FingerprintMismatchError,
    ApprovalInvalidError,
    StaleApprovalVersionError,
    DuplicateDecisionError,
    InvalidStateTransitionError,
)


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_concurrency_security.db")


@pytest.fixture
def engine(temp_db_path):
    repo = PolicyRepository(db_path=temp_db_path)
    return ApprovalEngine(repository=repo)


def test_concurrent_approval_decisions(engine):
    """
    Test concurrent decision submission against the same pending approval request.
    Verifies that optimistic locking and database constraints guarantee deterministic execution:
    exactly ONE decision succeeds, while the other fails.
    """
    now = time.time()
    req = engine.create_approval_request(
        principal_id="user-requester",
        principal_type=PrincipalType.USER,
        action="system.shutdown",
        resource="system",
        scope="admin_scope",
        risk_level=RiskLevel.HIGH,
        reason="Testing concurrency",
    )
    appr_id = req.approval_id

    user_principal = Principal(principal_id="user-approver", principal_type=PrincipalType.USER, permissions=["admin"])

    results = []
    errors = []

    def attempt_approve():
        try:
            res = engine.approve_request(appr_id, user_principal, session_valid=True)
            results.append(("APPROVED", res))
        except Exception as e:
            errors.append(e)

    def attempt_reject():
        try:
            res = engine.reject_request(appr_id, "user-rejecter", reason="Race reject")
            results.append(("REJECTED", res))
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_approve)
        f2 = executor.submit(attempt_reject)
        concurrent.futures.wait([f1, f2])

    assert len(results) == 1, f"Expected exactly 1 successful decision, got {len(results)}"
    assert len(errors) == 1, f"Expected exactly 1 error, got {len(errors)}"

    # Check terminal status in database
    final = engine.get_approval(appr_id)
    assert final.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


def test_agent_self_approval_prevention(engine):
    req = engine.create_approval_request(
        principal_id="agent-007",
        principal_type=PrincipalType.AGENT,
        action="network.scan",
        resource="local_net",
        scope="net_scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Agent operation",
    )

    agent_principal = Principal(principal_id="agent-007", principal_type=PrincipalType.AGENT, permissions=["scan"])

    # Agent cannot approve its own operation
    with pytest.raises(AuthorizationDeniedError, match="cannot approve its own operation"):
        engine.approve_request(req.approval_id, agent_principal, session_valid=True)


def test_agent_high_risk_approval_restriction(engine):
    req = engine.create_approval_request(
        principal_id="user-victim",
        principal_type=PrincipalType.USER,
        action="file.delete_all",
        resource="/system",
        scope="root",
        risk_level=RiskLevel.HIGH,
        reason="Destructive operation",
    )

    agent_principal = Principal(principal_id="agent-rogue", principal_type=PrincipalType.AGENT, permissions=["delete"])

    # Agent cannot approve HIGH/CRITICAL risk operation
    with pytest.raises(AuthorizationDeniedError, match="cannot approve HIGH risk"):
        engine.approve_request(req.approval_id, agent_principal, session_valid=True)


def test_invalid_session_denial(engine):
    req = engine.create_approval_request(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        action="system.reboot",
        resource="system",
        scope="reboot_scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Reboot request",
    )

    user_principal = Principal(principal_id="user-admin", principal_type=PrincipalType.USER, permissions=["reboot"])

    # Unauthenticated/invalid session denies decision
    with pytest.raises(AuthorizationDeniedError, match="session required"):
        engine.approve_request(req.approval_id, user_principal, session_valid=False)


def test_action_fingerprint_mismatch(engine):
    req = engine.create_approval_request(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        action="file.read",
        resource="/data/sensitive.txt",
        scope="read_scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Read file",
    )

    user_principal = Principal(principal_id="user-admin", principal_type=PrincipalType.USER, permissions=["read"])

    # Fingerprint check fails if mismatch
    with pytest.raises(FingerprintMismatchError):
        engine.approve_request(req.approval_id, user_principal, session_valid=True, expected_fingerprint="fp-tampered")


def test_consumption_scope_mismatch(engine):
    req = engine.create_approval_request(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        action="file.read",
        resource="/data/allowed.txt",
        scope="read_scope",
        risk_level=RiskLevel.MEDIUM,
        reason="Read file",
    )
    user_principal = Principal(principal_id="user-admin", principal_type=PrincipalType.USER, permissions=["read"])
    approved = engine.approve_request(req.approval_id, user_principal, session_valid=True)

    # Attempting to consume for different action fails
    mismatched_action_req = AuthorizationRequest(
        principal=user_principal,
        action="file.delete",  # Approved for file.read
        resource="/data/allowed.txt",
    )
    with pytest.raises(ApprovalInvalidError, match="action mismatch"):
        engine.consume_approval(approved.approval_id, mismatched_action_req)

    # Attempting to consume for different resource outside scope fails
    mismatched_resource_req = AuthorizationRequest(
        principal=user_principal,
        action="file.read",
        resource="/etc/shadow",  # Outside /data/allowed.txt
    )
    with pytest.raises(ApprovalInvalidError, match="resource mismatch"):
        engine.consume_approval(approved.approval_id, mismatched_resource_req)
