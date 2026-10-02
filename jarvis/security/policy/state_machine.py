"""
Approval State Machine and Action Fingerprinting for JARVIS (Batch 18).

Enforces deterministic status transitions, terminal state immutability,
and action fingerprint verification.
"""

import hashlib
import json
import time
from typing import Dict, Any, Optional, Set

from jarvis.security.policy.models import ApprovalStatus, ApprovalRequest
from jarvis.security.policy.exceptions import (
    InvalidStateTransitionError,
    DuplicateDecisionError,
    ApprovalExpiredError,
    FingerprintMismatchError,
)


def compute_request_fingerprint(
    requested_action: str,
    target_resource: str,
    exact_scope: str,
    risk_level: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for an action request.

    Excludes non-semantic fields (like timestamps, display IDs, credentials).
    Covered fields:
    - requested_action
    - target_resource
    - exact_scope
    - risk_level (as string)
    - params (sorted JSON representation of non-sensitive parameters)
    """
    normalized_params: Dict[str, Any] = {}
    if params:
        # Filter out obvious secrets or non-semantic display fields
        sensitive_keys = {"password", "secret", "token", "pin", "key", "auth", "timestamp", "display_name"}
        for k, v in sorted(params.items()):
            if k.lower() not in sensitive_keys:
                normalized_params[k] = str(v)

    payload = {
        "action": requested_action.strip().lower(),
        "resource": target_resource.strip(),
        "scope": exact_scope.strip(),
        "risk_level": str(risk_level).upper(),
        "params": normalized_params,
    }

    raw = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"fp-{digest[:32]}"


class ApprovalStateMachine:
    """
    Authoritative state machine governing approval lifecycle transitions.
    """

    ALLOWED_TRANSITIONS: Dict[ApprovalStatus, Set[ApprovalStatus]] = {
        ApprovalStatus.PENDING: {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        },
        ApprovalStatus.APPROVED: {
            ApprovalStatus.CONSUMED,
        },
        ApprovalStatus.REJECTED: set(),
        ApprovalStatus.EXPIRED: set(),
        ApprovalStatus.CANCELLED: set(),
        ApprovalStatus.CONSUMED: set(),
    }

    TERMINAL_STATES: Set[ApprovalStatus] = {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.CANCELLED,
        ApprovalStatus.CONSUMED,
    }

    @classmethod
    def can_transition(cls, current_status: ApprovalStatus, target_status: ApprovalStatus) -> bool:
        """Returns True if transition from current_status to target_status is permitted."""
        allowed = cls.ALLOWED_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @classmethod
    def validate_transition(
        cls,
        current_status: ApprovalStatus,
        target_status: ApprovalStatus,
    ) -> None:
        """
        Validates that a transition from current_status to target_status is legal.

        Raises:
            DuplicateDecisionError: if target_status equals current_status and is a decision state.
            InvalidStateTransitionError: if transition is forbidden by state machine rules.
        """
        if current_status == target_status:
            if current_status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
                raise DuplicateDecisionError(
                    f"Approval is already in terminal decision state '{current_status.value}'."
                )
            raise InvalidStateTransitionError(
                f"Cannot transition approval from '{current_status.value}' to itself."
            )

        allowed = cls.ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid approval transition from '{current_status.value}' to '{target_status.value}'."
            )

    @classmethod
    def validate_not_expired(cls, approval: ApprovalRequest, now: Optional[float] = None) -> None:
        """
        Validates that an approval request has not reached its expiration timestamp.

        Raises:
            ApprovalExpiredError: if current time >= approval.expires_at.
        """
        current_time = now if now is not None else time.time()
        if current_time >= approval.expires_at:
            raise ApprovalExpiredError(
                f"Approval '{approval.approval_id}' expired at {approval.expires_at} (current: {current_time})."
            )

    @classmethod
    def validate_fingerprint(cls, approval: ApprovalRequest, expected_fingerprint: str) -> None:
        """
        Validates that the provided action fingerprint matches the persisted request fingerprint.

        Raises:
            FingerprintMismatchError: if fingerprints do not match.
        """
        stored_fp = approval.request_fingerprint or approval.operation_fingerprint
        if stored_fp and expected_fingerprint and stored_fp != expected_fingerprint:
            raise FingerprintMismatchError(
                f"Action fingerprint mismatch for approval '{approval.approval_id}': "
                f"expected '{expected_fingerprint}', stored '{stored_fp}'."
            )
