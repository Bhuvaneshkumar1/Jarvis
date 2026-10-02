"""
Backward-Compatible Delegation Bridge to Centralized Security Policy Engine (Batch 15).
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel
from jarvis.core.config import get_settings
from jarvis.security.policy import (
    PolicyEngine as CentralPolicyEngine,
    AuthorizationRequest,
    Principal,
    PrincipalType,
    RiskLevel as PolicyRiskLevel,
)


class ActionType(str, Enum):
    READ = "READ"
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    EXECUTE_COMMAND = "EXECUTE_COMMAND"
    GIT_COMMIT = "GIT_COMMIT"
    GIT_PUSH = "GIT_PUSH"
    FINANCIAL = "FINANCIAL"
    EXTERNAL_API_CALL = "EXTERNAL_API_CALL"
    SYSTEM_CONTROL = "SYSTEM_CONTROL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionRequest(BaseModel):
    action_type: ActionType
    target: str
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: Dict[str, Any] = {}
    user_approved: bool = False
    task_has_explicit_modify_approval: bool = False


class PolicyDecision(BaseModel):
    allowed: bool
    requires_user_approval: bool = False
    reason: str
    risk_level: RiskLevel


class PolicyEngine:
    """
    Security & Authorization Policy Engine enforcing Rule 10 and Rule 26 (Fail Closed).
    Wraps the Centralized Security Policy Engine (Batch 15).
    """

    def __init__(self, settings=None, central_engine: Optional[CentralPolicyEngine] = None):
        self.settings = settings or get_settings()
        self.central_engine = central_engine or CentralPolicyEngine()

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        principal = Principal(
            principal_id=request.metadata.get("principal_id", "user"),
            principal_type=PrincipalType.USER,
            permissions=["*"],
        )

        meta = dict(request.metadata)
        if request.task_has_explicit_modify_approval:
            meta["task_has_explicit_modify_approval"] = True

        auth_req = AuthorizationRequest(
            principal=principal,
            action=request.action_type.value,
            resource=request.target,
            requested_risk_level=PolicyRiskLevel(request.risk_level.value),
            user_approved=request.user_approved,
            metadata=meta,
        )

        # Handle task_has_explicit_modify_approval or user_approved override
        if request.action_type == ActionType.MODIFY and request.task_has_explicit_modify_approval:
            auth_req.user_approved = True

        decision = self.central_engine.evaluate(auth_req)

        return PolicyDecision(
            allowed=decision.allowed,
            requires_user_approval=decision.requires_user_approval,
            reason=decision.reason,
            risk_level=RiskLevel(decision.effective_risk.value),
        )
