"""
Baseline Security Policy Rules A-G Evaluator for JARVIS (Batch 15).
"""

from typing import Tuple
from jarvis.security.policy.models import (
    AuthorizationRequest,
    PolicyDecisionType,
    RiskLevel,
    CyberScopeCategory,
)
from jarvis.security.policy.permissions import normalize_permission_name
from jarvis.security.policy.scope import validate_cybersecurity_scope
from jarvis.security.policy.exceptions import CyberAuthorizationError


def evaluate_baseline_rules(
    request: AuthorizationRequest,
    effective_risk: RiskLevel,
    workspace_root: str = "D:\\Projects",
) -> Tuple[PolicyDecisionType, str, str]:
    """
    Evaluates baseline security policies A-G deterministically.
    Returns Tuple of (PolicyDecisionType, reason_code, reason_description).
    """
    perm_norm = normalize_permission_name(request.action)

    # -------------------------------------------------------------
    # Policy G: Cybersecurity Operations
    # -------------------------------------------------------------
    if perm_norm.startswith("security."):
        if perm_norm in ["security.exploit", "security.credential_test", "security.modify_target", "security.scan"]:
            try:
                scope_cat = validate_cybersecurity_scope(
                    action=perm_norm,
                    target_resource=request.resource,
                    cyber_context=request.cyber_context,
                )
                if scope_cat == CyberScopeCategory.UNKNOWN_TARGET:
                    return PolicyDecisionType.DENY, "CYBER_UNKNOWN_TARGET", "Cybersecurity operation strictly denied against unknown target."
            except CyberAuthorizationError as e:
                return PolicyDecisionType.DENY, "CYBER_SCOPE_DENIAL", str(e)

            # Active ops require explicit approval
            if perm_norm in ["security.exploit", "security.modify_target"]:
                return (
                    PolicyDecisionType.REQUIRE_APPROVAL,
                    "CYBER_ACTIVE_OP_APPROVAL_REQ",
                    f"Active cybersecurity operation '{perm_norm}' requires explicit user approval.",
                )

        elif perm_norm in ["security.recon", "security.analyze"]:
            # Passive analysis allowed if scope is verified
            if not request.cyber_context or request.cyber_context.scope_category == CyberScopeCategory.UNKNOWN_TARGET:
                return PolicyDecisionType.DENY, "CYBER_UNAUTHORIZED_TARGET", "Passive security analysis denied against unknown target."

    # -------------------------------------------------------------
    # Policy E: Git Operations
    # -------------------------------------------------------------
    if perm_norm == "git.status":
        return PolicyDecisionType.ALLOW, "GIT_STATUS_PERMITTED", "Reading Git repository status permitted."

    if perm_norm == "git.commit":
        if not request.user_approved and not request.approval_id:
            return PolicyDecisionType.REQUIRE_APPROVAL, "GIT_COMMIT_APPROVAL_REQ", "Git commit requires explicit user approval."

    if perm_norm == "git.push":
        if not request.user_approved and not request.approval_id:
            return PolicyDecisionType.REQUIRE_APPROVAL, "GIT_PUSH_APPROVAL_REQ", "Git push requires explicit user approval."

    # -------------------------------------------------------------
    # Policy D: File Deletion
    # -------------------------------------------------------------
    if perm_norm in ["filesystem.delete", "code.delete"]:
        if not request.resource or request.resource.strip() in ["*", "/", "\\", "C:\\", "D:\\"]:
            return PolicyDecisionType.DENY, "AMBIGUOUS_DELETION_TARGET", "Ambiguous or root deletion target strictly denied."

        if not request.user_approved and not request.approval_id:
            return PolicyDecisionType.REQUIRE_APPROVAL, "FILE_DELETE_APPROVAL_REQ", "Deleting existing files requires explicit user approval."

    # -------------------------------------------------------------
    # Policy C: File Modification
    # -------------------------------------------------------------
    if perm_norm in ["filesystem.modify", "code.modify", "filesystem.rename", "filesystem.move"]:
        if not request.user_approved and not request.approval_id:
            return PolicyDecisionType.REQUIRE_APPROVAL, "FILE_MODIFY_APPROVAL_REQ", "Modifying existing files requires explicit approval."

    # -------------------------------------------------------------
    # Policy B: File Creation
    # -------------------------------------------------------------
    if perm_norm in ["filesystem.create", "code.create"]:
        # Verify write isn't outside workspace / sensitive location
        sensitive_dirs = ["C:\\Windows", "C:\\Program Files", "data\\credentials", "secrets"]
        res_lower = request.resource.lower()
        if any(s.lower() in res_lower for s in sensitive_dirs):
            return PolicyDecisionType.DENY, "SENSITIVE_DIRECTORY_WRITE_DENIED", f"File creation in sensitive location '{request.resource}' denied."

        return PolicyDecisionType.ALLOW, "FILE_CREATE_PERMITTED", "File creation permitted within authorized scope."

    # -------------------------------------------------------------
    # Policy A: File Reading
    # -------------------------------------------------------------
    if perm_norm in ["filesystem.read", "code.read", "system.settings.read"]:
        sensitive_read_targets = ["credentials", "secrets", "shadow", "sam", "config/master"]
        res_lower = request.resource.lower()
        if any(s in res_lower for s in sensitive_read_targets):
            return (
                PolicyDecisionType.REQUIRE_APPROVAL,
                "SENSITIVE_READ_APPROVAL_REQ",
                f"Reading credential/secret resource '{request.resource}' requires approval.",
            )

        return PolicyDecisionType.ALLOW, "FILE_READ_PERMITTED", "File reading permitted by default for authorized operations."

    # -------------------------------------------------------------
    # Policy F: High-Risk & Critical Operations
    # -------------------------------------------------------------
    if effective_risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        if not request.user_approved and not request.approval_id:
            return (
                PolicyDecisionType.REQUIRE_APPROVAL,
                "HIGH_RISK_APPROVAL_REQ",
                f"Operation '{request.action}' classified as {effective_risk.value} risk requires explicit approval.",
            )

    # Default fallback
    if request.user_approved or request.approval_id:
        return PolicyDecisionType.ALLOW, "EXPLICITLY_APPROVED", "Operation permitted following explicit approval."

    return PolicyDecisionType.ALLOW, "POLICY_DEFAULT_ALLOW", "Operation permitted by default policy."
