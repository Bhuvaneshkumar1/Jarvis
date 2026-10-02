"""
Centralized Authoritative Policy Decision Engine for JARVIS (Batch 15).
"""

import uuid
from typing import Optional, Any, List
from jarvis.security.policy.models import (
    AuthorizationRequest,
    PolicyDecision,
    PolicyDecisionType,
    RiskLevel,
    PrincipalType,
    ApprovalStatus,
)
from jarvis.security.policy.permissions import has_explicit_permission, normalize_permission_name
from jarvis.security.policy.risk import classify_risk
from jarvis.security.policy.scope import normalize_resource_path
from jarvis.security.policy.rules import evaluate_baseline_rules
from jarvis.security.policy.approval import ApprovalEngine
from jarvis.security.policy.events import (
    PolicyAuditIntegrator,
    PolicyEvaluationStartedEvent,
    PolicyDecisionAllowedEvent,
    PolicyDecisionDeniedEvent,
    PolicyApprovalRequiredEvent,
)
from jarvis.security.policy.exceptions import ScopeViolationError


class PolicyEngine:
    """
    Authoritative Centralized Security Policy & Decision Engine.
    Evaluates all JARVIS operations fail-closed through a deterministic 10-step pipeline.
    """

    def __init__(
        self,
        approval_engine: Optional[ApprovalEngine] = None,
        audit_integrator: Optional[PolicyAuditIntegrator] = None,
        auth_manager: Optional[Any] = None,
    ) -> None:
        self.approval_engine = approval_engine or ApprovalEngine()
        self.audit_integrator = audit_integrator or PolicyAuditIntegrator()
        self.auth_manager = auth_manager

    def evaluate(
        self,
        request: AuthorizationRequest,
        skip_approval_check: bool = False,
    ) -> PolicyDecision:
        """
        Deterministic 10-Step Policy Evaluation Workflow.
        Fails closed on any error or missing requirement.
        """
        correlation_id = request.correlation_id or f"corr-{uuid.uuid4().hex[:12]}"

        # Publish evaluation start event
        try:
            self.audit_integrator.publish_and_log(
                event=PolicyEvaluationStartedEvent(
                    payload={
                        "request_id": request.request_id,
                        "principal_id": request.principal.principal_id,
                        "action": request.action,
                        "resource": request.resource,
                    }
                ),
                action="POLICY_EVALUATION_START",
                result="STARTED",
                task_id=request.task_id,
                correlation_id=correlation_id,
                fail_closed=False,
            )
        except Exception:
            pass

        try:
            # Step 1: Principal identity validity
            if not request.principal or not request.principal.principal_id:
                return self._deny(request, RiskLevel.HIGH, "INVALID_PRINCIPAL", "Principal identity is missing or empty.", correlation_id)

            # Step 2: Authentication and session validity
            if request.principal.principal_type == PrincipalType.USER and request.session_id:
                if self.auth_manager:
                    try:
                        sess = self.auth_manager.get_session(request.session_id)
                        if not sess or not sess.is_active:
                            return self._deny(
                                request,
                                RiskLevel.HIGH,
                                "INVALID_SESSION",
                                f"User session '{request.session_id}' is invalid, expired, or revoked.",
                                correlation_id,
                            )
                    except Exception:
                        return self._deny(
                            request,
                            RiskLevel.HIGH,
                            "AUTH_CHECK_FAILED",
                            "Session validation check failed unexpectedly.",
                            correlation_id,
                        )

            # Step 3: Principal status / delegation limits
            if request.principal.principal_type == PrincipalType.AGENT:
                if request.principal.delegation_depth > 5:
                    return self._deny(
                        request,
                        RiskLevel.HIGH,
                        "DELEGATION_DEPTH_EXCEEDED",
                        "Agent delegation depth exceeds safety threshold.",
                        correlation_id,
                    )

            # Step 4: Permission grants and explicit denials
            perm_norm = normalize_permission_name(request.action)
            if not has_explicit_permission(request.principal, perm_norm):
                return self._deny(
                    request,
                    RiskLevel.MEDIUM,
                    "PERMISSION_DENIED",
                    f"Principal '{request.principal.principal_id}' lacks permission '{perm_norm}'.",
                    correlation_id,
                )

            # Step 5: Resource and path restrictions
            norm_res = request.resource
            if perm_norm.startswith("filesystem.") or perm_norm.startswith("code."):
                try:
                    norm_res = normalize_resource_path(request.resource)
                except ScopeViolationError as e:
                    return self._deny(request, RiskLevel.HIGH, "INVALID_RESOURCE_PATH", str(e), correlation_id)

            # Step 6: Requested scope
            # (Checked within baseline rules / scope module)

            # Step 7: Risk classification
            effective_risk = classify_risk(
                action=request.action,
                resource=norm_res,
                principal=request.principal,
                requested_risk=request.requested_risk_level,
                metadata=request.metadata,
            )

            # Step 8: Scoped approval check
            if not skip_approval_check and not request.user_approved and not request.approval_id:
                if self.approval_engine.is_action_covered_by_scoped_approval(
                    principal_id=request.principal.principal_id,
                    action=request.action,
                    resource=norm_res,
                    risk_level=effective_risk,
                    task_id=request.task_id,
                ):
                    return self._allow(
                        request=request,
                        effective_risk=effective_risk,
                        reason_code="SCOPED_APPROVAL_MATCH",
                        reason="Operation authorized under active scoped approval.",
                        applicable_policies=["SCOPED_APPROVAL_POLICY"],
                        correlation_id=correlation_id,
                    )

            # Step 9: Specific approval binding validation if approval_id supplied
            if request.approval_id and not skip_approval_check:
                appr = self.approval_engine.get_approval(request.approval_id)
                if not appr:
                    return self._deny(
                        request,
                        effective_risk,
                        "APPROVAL_NOT_FOUND",
                        f"Specified approval ID '{request.approval_id}' not found.",
                        correlation_id,
                    )
                if appr.status != ApprovalStatus.APPROVED:
                    return self._deny(
                        request,
                        effective_risk,
                        "APPROVAL_INVALID_STATE",
                        f"Approval '{request.approval_id}' is in state '{appr.status.value}', expected APPROVED.",
                        correlation_id,
                    )

            # Step 10: Baseline Rules A-G Evaluation
            rule_decision, reason_code, reason_desc = evaluate_baseline_rules(
                request=request,
                effective_risk=effective_risk,
            )

            if rule_decision == PolicyDecisionType.DENY:
                return self._deny(request, effective_risk, reason_code, reason_desc, correlation_id)

            if rule_decision == PolicyDecisionType.REQUIRE_APPROVAL:
                # Check if approval requested or created
                req_appr_id = request.approval_id
                if not req_appr_id:
                    # Auto-create pending approval request in database
                    created_appr = self.approval_engine.create_approval_request(
                        principal_id=request.principal.principal_id,
                        principal_type=request.principal.principal_type,
                        action=request.action,
                        resource=norm_res,
                        scope=request.requested_scope or "task_scope",
                        risk_level=effective_risk,
                        reason=reason_desc,
                        task_id=request.task_id,
                        correlation_id=correlation_id,
                    )
                    req_appr_id = created_appr.approval_id

                return self._require_approval(
                    request=request,
                    effective_risk=effective_risk,
                    reason_code=reason_code,
                    reason=reason_desc,
                    approval_id=req_appr_id,
                    correlation_id=correlation_id,
                )

            # Default Allow
            return self._allow(
                request=request,
                effective_risk=effective_risk,
                reason_code=reason_code,
                reason=reason_desc,
                applicable_policies=["BASELINE_RULES_POLICY"],
                correlation_id=correlation_id,
            )

        except Exception as e:
            # Fail closed on unhandled error
            return self._deny(
                request=request,
                effective_risk=RiskLevel.CRITICAL,
                reason_code="FAIL_CLOSED_UNHANDLED_EXCEPTION",
                reason=f"FAIL CLOSED: Policy engine encountered an unhandled exception: {str(e)}",
                correlation_id=correlation_id,
            )

    def _allow(
        self,
        request: AuthorizationRequest,
        effective_risk: RiskLevel,
        reason_code: str,
        reason: str,
        applicable_policies: List[str],
        correlation_id: str,
    ) -> PolicyDecision:
        dec = PolicyDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            principal_id=request.principal.principal_id,
            principal_type=request.principal.principal_type,
            action=request.action,
            resource=request.resource,
            requested_scope=request.requested_scope,
            effective_risk=effective_risk,
            decision=PolicyDecisionType.ALLOW,
            allowed=True,
            requires_user_approval=False,
            reason_code=reason_code,
            reason=reason,
            applicable_policies=applicable_policies,
            required_approval_id=request.approval_id,
            correlation_id=correlation_id,
        )
        self.audit_integrator.publish_and_log(
            event=PolicyDecisionAllowedEvent(payload=dec.model_dump()),
            action="POLICY_DECISION",
            result="ALLOW",
            task_id=request.task_id,
            correlation_id=correlation_id,
        )
        return dec

    def _deny(
        self,
        request: AuthorizationRequest,
        effective_risk: RiskLevel,
        reason_code: str,
        reason: str,
        correlation_id: str,
    ) -> PolicyDecision:
        dec = PolicyDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            principal_id=request.principal.principal_id if request.principal else "UNKNOWN",
            principal_type=request.principal.principal_type if request.principal else PrincipalType.USER,
            action=request.action,
            resource=request.resource,
            requested_scope=request.requested_scope,
            effective_risk=effective_risk,
            decision=PolicyDecisionType.DENY,
            allowed=False,
            requires_user_approval=False,
            reason_code=reason_code,
            reason=reason,
            applicable_policies=["FAIL_CLOSED_SECURITY_POLICY"],
            correlation_id=correlation_id,
        )
        self.audit_integrator.publish_and_log(
            event=PolicyDecisionDeniedEvent(payload=dec.model_dump()),
            action="POLICY_DECISION",
            result="DENY",
            task_id=request.task_id,
            correlation_id=correlation_id,
            error=reason,
        )
        return dec

    def _require_approval(
        self,
        request: AuthorizationRequest,
        effective_risk: RiskLevel,
        reason_code: str,
        reason: str,
        approval_id: str,
        correlation_id: str,
    ) -> PolicyDecision:
        dec = PolicyDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            principal_id=request.principal.principal_id,
            principal_type=request.principal.principal_type,
            action=request.action,
            resource=request.resource,
            requested_scope=request.requested_scope,
            effective_risk=effective_risk,
            decision=PolicyDecisionType.REQUIRE_APPROVAL,
            allowed=False,
            requires_user_approval=True,
            reason_code=reason_code,
            reason=reason,
            applicable_policies=["APPROVAL_REQUIRED_POLICY"],
            required_approval_id=approval_id,
            correlation_id=correlation_id,
        )
        self.audit_integrator.publish_and_log(
            event=PolicyApprovalRequiredEvent(payload=dec.model_dump()),
            action="POLICY_DECISION",
            result="REQUIRE_APPROVAL",
            task_id=request.task_id,
            correlation_id=correlation_id,
            details={"approval_id": approval_id},
        )
        return dec
