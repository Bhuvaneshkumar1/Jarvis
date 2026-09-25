from enum import Enum
from typing import Dict, Any
from pydantic import BaseModel
from jarvis.core.config import get_settings

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
    One single authoritative policy implementation.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        # 1. READ Operations
        if request.action_type == ActionType.READ:
            return PolicyDecision(
                allowed=True,
                requires_user_approval=False,
                reason="READ operations are allowed by default under Rule 10.",
                risk_level=request.risk_level,
            )

        # 2. CREATE Operations
        if request.action_type == ActionType.CREATE:
            if self.settings.allow_auto_create:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason="CREATE operation permitted under task creation policy.",
                    risk_level=request.risk_level,
                )
            elif request.user_approved:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason="CREATE operation explicitly approved by user.",
                    risk_level=request.risk_level,
                )
            else:
                return PolicyDecision(
                    allowed=False,
                    requires_user_approval=True,
                    reason="CREATE operation requires explicit user approval.",
                    risk_level=request.risk_level,
                )

        # 3. MODIFY / UPDATE Operations
        if request.action_type == ActionType.MODIFY:
            if request.task_has_explicit_modify_approval or request.user_approved:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason="MODIFY permitted by task approval scope or user approval.",
                    risk_level=request.risk_level,
                )
            if self.settings.require_approval_for_modify:
                return PolicyDecision(
                    allowed=False,
                    requires_user_approval=True,
                    reason="Modification of existing target requires explicit user approval (Rule 10).",
                    risk_level=RiskLevel.MEDIUM,
                )

        # 4. DELETE Operations
        if request.action_type == ActionType.DELETE:
            if request.user_approved:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason="DELETE operation approved by user.",
                    risk_level=request.risk_level,
                )
            return PolicyDecision(
                allowed=False,
                requires_user_approval=True,
                reason="DELETION requires explicit user approval under Rule 10.",
                risk_level=RiskLevel.HIGH,
            )

        # 5. GIT COMMIT / PUSH Operations
        if request.action_type in [ActionType.GIT_COMMIT, ActionType.GIT_PUSH]:
            if request.user_approved:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason=f"{request.action_type} approved by user.",
                    risk_level=request.risk_level,
                )
            return PolicyDecision(
                allowed=False,
                requires_user_approval=True,
                reason=f"{request.action_type} requires explicit user approval under Rule 10.",
                risk_level=RiskLevel.HIGH,
            )

        # 6. FINANCIAL Operations
        if request.action_type == ActionType.FINANCIAL:
            if request.user_approved:
                return PolicyDecision(
                    allowed=True,
                    requires_user_approval=False,
                    reason="FINANCIAL action approved by user.",
                    risk_level=RiskLevel.CRITICAL,
                )
            return PolicyDecision(
                allowed=False,
                requires_user_approval=True,
                reason="FINANCIAL operations strictly require explicit user approval (Rule 10).",
                risk_level=RiskLevel.CRITICAL,
            )

        # 7. HIGH / CRITICAL RISK Operations Fail-Closed check
        if request.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            if not request.user_approved:
                return PolicyDecision(
                    allowed=False,
                    requires_user_approval=True,
                    reason=f"Action marked as {request.risk_level} risk level requires user approval (Rule 10/26).",
                    risk_level=request.risk_level,
                )

        # Default Fail-Closed (Rule 26)
        if request.user_approved:
            return PolicyDecision(
                allowed=True,
                requires_user_approval=False,
                reason="Action permitted following explicit user approval.",
                risk_level=request.risk_level,
            )

        return PolicyDecision(
            allowed=False,
            requires_user_approval=True,
            reason="FAIL CLOSED: Action not explicitly authorized by security policy (Rule 26).",
            risk_level=request.risk_level,
        )
