"""
Unit Tests for Approval State Machine & Action Fingerprinting (Batch 18).
"""

import pytest
import time
from jarvis.security.policy.models import ApprovalRequest, ApprovalStatus
from jarvis.security.policy.state_machine import (
    ApprovalStateMachine,
    compute_request_fingerprint,
)
from jarvis.security.policy.exceptions import (
    InvalidStateTransitionError,
    DuplicateDecisionError,
    ApprovalExpiredError,
    FingerprintMismatchError,
)


def test_fingerprint_computation_deterministic():
    fp1 = compute_request_fingerprint("cmd.exec", "system:shell", "read_only", "HIGH", {"param1": "val1"})
    fp2 = compute_request_fingerprint("cmd.exec", "system:shell", "read_only", "HIGH", {"param1": "val1"})
    assert fp1 == fp2
    assert fp1.startswith("fp-")


def test_fingerprint_computation_changes_with_parameters():
    fp1 = compute_request_fingerprint("cmd.exec", "system:shell", "read_only", "HIGH", {"param1": "val1"})
    fp2 = compute_request_fingerprint("cmd.exec", "system:shell", "read_only", "HIGH", {"param1": "val2"})
    assert fp1 != fp2


def test_state_machine_valid_transitions():
    # PENDING -> APPROVED
    ApprovalStateMachine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
    # PENDING -> REJECTED
    ApprovalStateMachine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.REJECTED)
    # PENDING -> EXPIRED
    ApprovalStateMachine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.EXPIRED)
    # PENDING -> CANCELLED
    ApprovalStateMachine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.CANCELLED)
    # APPROVED -> CONSUMED
    ApprovalStateMachine.validate_transition(ApprovalStatus.APPROVED, ApprovalStatus.CONSUMED)


def test_state_machine_duplicate_decision_rejected():
    with pytest.raises(DuplicateDecisionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.APPROVED, ApprovalStatus.APPROVED)

    with pytest.raises(DuplicateDecisionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.REJECTED, ApprovalStatus.REJECTED)


def test_state_machine_prohibited_transitions():
    with pytest.raises(InvalidStateTransitionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.REJECTED, ApprovalStatus.APPROVED)

    with pytest.raises(InvalidStateTransitionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.EXPIRED, ApprovalStatus.APPROVED)

    with pytest.raises(InvalidStateTransitionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.CANCELLED, ApprovalStatus.APPROVED)

    with pytest.raises(InvalidStateTransitionError):
        ApprovalStateMachine.validate_transition(ApprovalStatus.CONSUMED, ApprovalStatus.APPROVED)


def test_state_machine_expiry_validation():
    now = time.time()
    req = ApprovalRequest(
        principal_id="user1",
        requested_action="cmd.exec",
        target_resource="shell",
        exact_scope="scope1",
        expires_at=now - 10,
    )
    with pytest.raises(ApprovalExpiredError):
        ApprovalStateMachine.validate_not_expired(req, now=now)


def test_state_machine_fingerprint_validation():
    req = ApprovalRequest(
        principal_id="user1",
        requested_action="cmd.exec",
        target_resource="shell",
        exact_scope="scope1",
        expires_at=time.time() + 3600,
        request_fingerprint="fp-1234567890abcdef",
    )

    # Matching
    ApprovalStateMachine.validate_fingerprint(req, "fp-1234567890abcdef")

    # Mismatch
    with pytest.raises(FingerprintMismatchError):
        ApprovalStateMachine.validate_fingerprint(req, "fp-different")
