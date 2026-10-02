"""
Centralized Policy, Security & Approval Subsystem for JARVIS (Batch 15).
Exports PolicyEngine, ApprovalEngine, Risk Classifier, Models, Exceptions, and Enums.
"""

from jarvis.security.policy.models import (
    Principal,
    PrincipalType,
    RiskLevel,
    PolicyDecisionType,
    ApprovalStatus,
    CyberScopeCategory,
    AuthorizationRequest,
    PolicyDecision,
    ApprovalRequest,
    ScopedApproval,
    CyberAuthorizationContext,
)
from jarvis.security.policy.permissions import (
    normalize_permission_name,
    has_explicit_permission,
    validate_delegation,
    FILESYSTEM_PERMISSIONS,
    SYSTEM_PERMISSIONS,
    DEVELOPMENT_PERMISSIONS,
    AGENT_PERMISSIONS,
    INTEGRATION_PERMISSIONS,
    CYBERSECURITY_PERMISSIONS,
)
from jarvis.security.policy.risk import classify_risk
from jarvis.security.policy.scope import (
    normalize_resource_path,
    is_path_in_scope,
    validate_cybersecurity_scope,
)
from jarvis.security.policy.store import PolicyRepository
from jarvis.security.policy.approval import ApprovalEngine
from jarvis.security.policy.engine import PolicyEngine
from jarvis.security.policy.events import PolicyAuditIntegrator
from jarvis.security.policy.exceptions import (
    PolicyError,
    AuthorizationDeniedError,
    ApprovalError,
    ApprovalRequiredError,
    ApprovalNotFoundError,
    ApprovalExpiredError,
    ApprovalAlreadyConsumedError,
    ApprovalInvalidError,
    ScopeViolationError,
    DelegationError,
    PolicyConfigurationError,
    CyberAuthorizationError,
)

__all__ = [
    "Principal",
    "PrincipalType",
    "RiskLevel",
    "PolicyDecisionType",
    "ApprovalStatus",
    "CyberScopeCategory",
    "AuthorizationRequest",
    "PolicyDecision",
    "ApprovalRequest",
    "ScopedApproval",
    "CyberAuthorizationContext",
    "normalize_permission_name",
    "has_explicit_permission",
    "validate_delegation",
    "FILESYSTEM_PERMISSIONS",
    "SYSTEM_PERMISSIONS",
    "DEVELOPMENT_PERMISSIONS",
    "AGENT_PERMISSIONS",
    "INTEGRATION_PERMISSIONS",
    "CYBERSECURITY_PERMISSIONS",
    "classify_risk",
    "normalize_resource_path",
    "is_path_in_scope",
    "validate_cybersecurity_scope",
    "PolicyRepository",
    "ApprovalEngine",
    "PolicyEngine",
    "PolicyAuditIntegrator",
    "PolicyError",
    "AuthorizationDeniedError",
    "ApprovalError",
    "ApprovalRequiredError",
    "ApprovalNotFoundError",
    "ApprovalExpiredError",
    "ApprovalAlreadyConsumedError",
    "ApprovalInvalidError",
    "ScopeViolationError",
    "DelegationError",
    "PolicyConfigurationError",
    "CyberAuthorizationError",
]
