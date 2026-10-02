"""
Centralized Persistent Approval Engine for JARVIS (Batch 15 & Batch 18).
"""

import time
import uuid
from typing import List, Optional, Any, Dict

from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    ScopedApproval,
    Principal,
    PrincipalType,
    RiskLevel,
    AuthorizationRequest,
    ApprovalDecisionRecord,
    ApprovalHistoryEntry,
)
from jarvis.security.policy.store import PolicyRepository
from jarvis.security.policy.state_machine import ApprovalStateMachine, compute_request_fingerprint
from jarvis.security.policy.scope import is_path_in_scope
from jarvis.security.policy.exceptions import (
    ApprovalNotFoundError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalInvalidError,
    AuthorizationDeniedError,
)
from jarvis.security.policy.events import (
    PolicyAuditIntegrator,
    PolicyApprovalRequestedEvent,
    PolicyApprovalApprovedEvent,
    PolicyApprovalRejectedEvent,
    PolicyApprovalExpiredEvent,
    PolicyApprovalCancelledEvent,
    PolicyApprovalConsumedEvent,
)


class ApprovalEngine:
    """
    Authoritative Persistent Approval Engine.
    Enforces atomic status transitions, expiration, single-use consumption, agent self-approval prevention,
    action fingerprint integrity, scoped approvals, task manager synchronization, and audit logging.
    """

    def __init__(
        self,
        repository: Optional[PolicyRepository] = None,
        audit_integrator: Optional[PolicyAuditIntegrator] = None,
        task_manager: Optional[Any] = None,
        default_expiration_seconds: float = 3600.0,
    ) -> None:
        self.repository = repository or PolicyRepository()
        self.audit_integrator = audit_integrator or PolicyAuditIntegrator()
        self.task_manager = task_manager
        self.default_expiration_seconds = default_expiration_seconds

    def create_approval_request(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        action: str,
        resource: str,
        scope: str,
        risk_level: RiskLevel,
        reason: str,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        expiration_seconds: Optional[float] = None,
        operation_fingerprint: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        now = time.time()
        ttl = expiration_seconds if expiration_seconds is not None else self.default_expiration_seconds
        expires_at = now + ttl

        fingerprint = operation_fingerprint or compute_request_fingerprint(
            requested_action=action,
            target_resource=resource,
            exact_scope=scope,
            risk_level=risk_level.value,
            params=params,
        )

        req = ApprovalRequest(
            approval_id=f"appr-{uuid.uuid4().hex[:12]}",
            principal_id=principal_id,
            principal_type=principal_type,
            requested_action=action,
            target_resource=resource,
            exact_scope=scope,
            risk_level=risk_level,
            reason=reason,
            task_id=task_id,
            correlation_id=correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
            created_at=now,
            expires_at=expires_at,
            status=ApprovalStatus.PENDING,
            operation_fingerprint=fingerprint,
            request_fingerprint=fingerprint,
            policy_version="1.0.0",
            version=1,
        )

        saved = self.repository.save_approval_request(req)

        # Audit and event publishing
        self.audit_integrator.publish_and_log(
            event=PolicyApprovalRequestedEvent(
                payload={
                    "approval_id": saved.approval_id,
                    "principal_id": saved.principal_id,
                    "action": saved.requested_action,
                    "resource": saved.target_resource,
                    "risk_level": saved.risk_level.value,
                    "fingerprint": fingerprint,
                    "task_id": saved.task_id,
                }
            ),
            action="CREATE_APPROVAL",
            result="PENDING",
            task_id=saved.task_id,
            correlation_id=saved.correlation_id,
            details={"approval_id": saved.approval_id, "expires_at": saved.expires_at},
        )

        return saved

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        return self.repository.get_approval_request(approval_id)

    def list_pending_approvals(self, principal_id: Optional[str] = None, task_id: Optional[str] = None) -> List[ApprovalRequest]:
        self.expire_approvals()
        return self.repository.list_pending_approvals(principal_id=principal_id, task_id=task_id)

    def list_approvals_by_status(self, status: ApprovalStatus, limit: int = 100, offset: int = 0) -> List[ApprovalRequest]:
        return self.repository.list_approvals_by_status(status=status, limit=limit, offset=offset)

    def list_approvals_in_time_range(self, start_time: float, end_time: float, limit: int = 100, offset: int = 0) -> List[ApprovalRequest]:
        return self.repository.list_approvals_in_time_range(start_time=start_time, end_time=end_time, limit=limit, offset=offset)

    def get_approval_history(self, approval_id: str) -> List[ApprovalHistoryEntry]:
        return self.repository.get_approval_history(approval_id)

    def get_approval_decisions(self, approval_id: str) -> List[ApprovalDecisionRecord]:
        return self.repository.get_approval_decisions(approval_id)

    def approve_request(
        self,
        approval_id: str,
        approver_principal: Principal,
        session_valid: bool = True,
        expected_fingerprint: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        Approve a pending approval request after authenticating the approver principal,
        verifying expiry, checking agent self-approval restrictions, and validating action fingerprint.
        """
        req = self.repository.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

        # Expiration check
        if time.time() >= req.expires_at:
            self.repository.update_approval_status(approval_id, ApprovalStatus.EXPIRED)
            raise ApprovalExpiredError(f"Approval '{approval_id}' has expired.")

        # Check duplicate decision / status transition
        if req.status != ApprovalStatus.PENDING:
            ApprovalStateMachine.validate_transition(req.status, ApprovalStatus.APPROVED)

        # Fingerprint check
        if expected_fingerprint:
            ApprovalStateMachine.validate_fingerprint(req, expected_fingerprint)

        # Session check for user approvals
        if not session_valid:
            self.audit_integrator.publish_and_log(
                event=PolicyApprovalRejectedEvent(payload={"approval_id": approval_id, "reason": "Invalid session"}),
                action="APPROVE_REQUEST",
                result="UNAUTHORIZED",
                task_id=req.task_id,
                correlation_id=req.correlation_id,
                details={"reason": "Invalid authenticated user session"},
            )
            raise AuthorizationDeniedError("Valid authenticated user session required to approve request.")

        # Agent Self-Approval Check
        if approver_principal.principal_type == PrincipalType.AGENT:
            if approver_principal.principal_id == req.principal_id:
                raise AuthorizationDeniedError(f"Agent '{approver_principal.principal_id}' cannot approve its own operation.")
            if req.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                raise AuthorizationDeniedError(f"Agent '{approver_principal.principal_id}' cannot approve {req.risk_level.value} risk operation.")

        updated = self.repository.update_approval_status(
            approval_id=approval_id,
            new_status=ApprovalStatus.APPROVED,
            approver_id=approver_principal.principal_id,
            expected_version=expected_version or req.version,
        )

        # Publish event & audit log
        self.audit_integrator.publish_and_log(
            event=PolicyApprovalApprovedEvent(
                payload={
                    "approval_id": updated.approval_id,
                    "approver_id": approver_principal.principal_id,
                    "action": updated.requested_action,
                    "task_id": updated.task_id,
                }
            ),
            action="APPROVE_REQUEST",
            result="APPROVED",
            task_id=updated.task_id,
            correlation_id=updated.correlation_id,
            details={"approver_id": approver_principal.principal_id},
        )

        # Sync task manager if linked
        if self.task_manager and updated.task_id:
            try:
                if hasattr(self.task_manager, "handle_approval_decision"):
                    self.task_manager.handle_approval_decision(
                        task_id=updated.task_id,
                        approval_id=updated.approval_id,
                        decision=ApprovalStatus.APPROVED,
                    )
            except Exception:
                # Log error, do not reverse committed decision
                pass

        return updated

    def reject_request(
        self,
        approval_id: str,
        rejecter_id: str,
        reason: str = "User rejected",
        expected_version: Optional[int] = None,
    ) -> ApprovalRequest:
        req = self.repository.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

        if req.status != ApprovalStatus.PENDING:
            ApprovalStateMachine.validate_transition(req.status, ApprovalStatus.REJECTED)

        updated = self.repository.update_approval_status(
            approval_id=approval_id,
            new_status=ApprovalStatus.REJECTED,
            approver_id=rejecter_id,
            reason=reason,
            expected_version=expected_version or req.version,
        )

        self.audit_integrator.publish_and_log(
            event=PolicyApprovalRejectedEvent(
                payload={
                    "approval_id": updated.approval_id,
                    "rejecter_id": rejecter_id,
                    "reason": reason,
                    "task_id": updated.task_id,
                }
            ),
            action="REJECT_REQUEST",
            result="REJECTED",
            task_id=updated.task_id,
            correlation_id=updated.correlation_id,
            details={"rejecter_id": rejecter_id, "reason": reason},
        )

        if self.task_manager and updated.task_id:
            try:
                if hasattr(self.task_manager, "handle_approval_decision"):
                    self.task_manager.handle_approval_decision(
                        task_id=updated.task_id,
                        approval_id=updated.approval_id,
                        decision=ApprovalStatus.REJECTED,
                    )
            except Exception:
                pass

        return updated

    def cancel_request(
        self,
        approval_id: str,
        canceller_id: str,
        reason: str = "Cancelled by requester",
        expected_version: Optional[int] = None,
    ) -> ApprovalRequest:
        req = self.repository.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

        if req.status != ApprovalStatus.PENDING:
            ApprovalStateMachine.validate_transition(req.status, ApprovalStatus.CANCELLED)

        updated = self.repository.update_approval_status(
            approval_id=approval_id,
            new_status=ApprovalStatus.CANCELLED,
            approver_id=canceller_id,
            reason=reason,
            expected_version=expected_version or req.version,
        )

        self.audit_integrator.publish_and_log(
            event=PolicyApprovalCancelledEvent(
                payload={
                    "approval_id": updated.approval_id,
                    "canceller_id": canceller_id,
                    "reason": reason,
                    "task_id": updated.task_id,
                }
            ),
            action="CANCEL_REQUEST",
            result="CANCELLED",
            task_id=updated.task_id,
            correlation_id=updated.correlation_id,
        )

        if self.task_manager and updated.task_id:
            try:
                if hasattr(self.task_manager, "handle_approval_decision"):
                    self.task_manager.handle_approval_decision(
                        task_id=updated.task_id,
                        approval_id=updated.approval_id,
                        decision=ApprovalStatus.CANCELLED,
                    )
            except Exception:
                pass

        return updated

    def expire_approvals(self, now: Optional[float] = None) -> int:
        expired_records = self.repository.expire_outdated_approvals(now=now)
        for req in expired_records:
            self.audit_integrator.publish_and_log(
                event=PolicyApprovalExpiredEvent(
                    payload={
                        "approval_id": req.approval_id,
                        "task_id": req.task_id,
                    }
                ),
                action="EXPIRE_APPROVAL",
                result="EXPIRED",
                task_id=req.task_id,
                correlation_id=req.correlation_id,
            )
            if self.task_manager and req.task_id:
                try:
                    if hasattr(self.task_manager, "handle_approval_decision"):
                        self.task_manager.handle_approval_decision(
                            task_id=req.task_id,
                            approval_id=req.approval_id,
                            decision=ApprovalStatus.EXPIRED,
                        )
                except Exception:
                    pass
        return len(expired_records)

    def consume_approval(
        self,
        approval_id: str,
        request: AuthorizationRequest,
        policy_evaluator_fn: Optional[Any] = None,
        expected_fingerprint: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Single-use atomic consumption of an approval immediately before execution.
        Re-validates target action, resource, task, fingerprint, expiration, and current security policy (TOCTOU protection).
        """
        req = self.repository.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval ID '{approval_id}' not found.")

        if req.status == ApprovalStatus.CONSUMED:
            raise ApprovalAlreadyConsumedError(f"Approval '{approval_id}' has already been consumed.")

        if req.status != ApprovalStatus.APPROVED:
            raise ApprovalInvalidError(f"Approval '{approval_id}' status is '{req.status.value}', expected APPROVED.")

        if time.time() >= req.expires_at:
            self.repository.update_approval_status(approval_id, ApprovalStatus.EXPIRED)
            raise ApprovalExpiredError(f"Approval '{approval_id}' has expired.")

        # Fingerprint verification
        if expected_fingerprint:
            ApprovalStateMachine.validate_fingerprint(req, expected_fingerprint)

        # Re-verify action & resource binding
        if req.requested_action.lower() != request.action.lower():
            raise ApprovalInvalidError(f"Approval action mismatch: approved '{req.requested_action}', requested '{request.action}'.")

        if not is_path_in_scope(request.resource, req.target_resource):
            raise ApprovalInvalidError(f"Approval resource mismatch: requested '{request.resource}' outside approved scope '{req.target_resource}'.")

        if req.task_id and request.task_id and req.task_id != request.task_id:
            raise ApprovalInvalidError(f"Approval task binding mismatch: approved for task '{req.task_id}', requested by '{request.task_id}'.")

        # TOCTOU protection: Re-evaluate policy if function provided
        if policy_evaluator_fn:
            current_decision = policy_evaluator_fn(request, skip_approval_check=True)
            if current_decision.decision == "DENY":
                raise AuthorizationDeniedError(f"TOCTOU Policy Check Failed: Policy has changed since approval creation. Reason: {current_decision.reason}")

        # Atomically consume
        consumed = self.repository.consume_approval_atomically(
            approval_id=approval_id,
            consumer_task_id=request.task_id,
        )

        self.audit_integrator.publish_and_log(
            event=PolicyApprovalConsumedEvent(
                payload={
                    "approval_id": consumed.approval_id,
                    "task_id": request.task_id,
                    "action": request.action,
                    "resource": request.resource,
                }
            ),
            action="CONSUME_APPROVAL",
            result="CONSUMED",
            task_id=request.task_id,
            correlation_id=request.correlation_id,
        )

        return consumed

    def create_scoped_approval(
        self,
        principal_id: str,
        allowed_actions: List[str],
        allowed_resources: List[str],
        task_id: Optional[str] = None,
        max_risk_level: RiskLevel = RiskLevel.MEDIUM,
        duration_seconds: float = 3600.0,
        delegation_permitted: bool = False,
        max_uses: Optional[int] = None,
    ) -> ScopedApproval:
        scoped = ScopedApproval(
            approval_id=f"scop-{uuid.uuid4().hex[:12]}",
            principal_id=principal_id,
            task_id=task_id,
            allowed_actions=allowed_actions,
            allowed_resources=allowed_resources,
            max_risk_level=max_risk_level,
            expires_at=time.time() + duration_seconds,
            delegation_permitted=delegation_permitted,
            max_uses=max_uses,
        )
        return self.repository.save_scoped_approval(scoped)

    def is_action_covered_by_scoped_approval(
        self,
        principal_id: str,
        action: str,
        resource: str,
        risk_level: RiskLevel,
        task_id: Optional[str] = None,
    ) -> bool:
        valid_scoped = self.repository.get_valid_scoped_approvals(principal_id=principal_id, task_id=task_id)

        RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        for s in valid_scoped:
            if s.task_id and task_id and s.task_id != task_id:
                continue

            if RISK_ORDER.index(risk_level) > RISK_ORDER.index(s.max_risk_level):
                continue

            action_lower = action.lower()
            if not any(a.lower() == action_lower or a == "*" for a in s.allowed_actions):
                continue

            res_matched = False
            for allowed_res in s.allowed_resources:
                if is_path_in_scope(resource, allowed_res):
                    res_matched = True
                    break

            if res_matched:
                self.repository.increment_scoped_approval_usage(s.approval_id)
                return True

        return False
