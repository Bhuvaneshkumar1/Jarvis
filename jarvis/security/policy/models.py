"""
Identity, Permission, Risk, Decision, and Approval Models for JARVIS Policy Engine (Batch 15).
"""

import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class PrincipalType(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    SCHEDULED_TASK = "SCHEDULED_TASK"
    INTEGRATION = "INTEGRATION"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_REAUTHENTICATION = "REQUIRE_REAUTHENTICATION"
    REQUIRE_ADDITIONAL_AUTHORIZATION = "REQUIRE_ADDITIONAL_AUTHORIZATION"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"


class CyberScopeCategory(str, Enum):
    LOCAL_LAB = "LOCAL_LAB"
    PERSONAL_INFRASTRUCTURE = "PERSONAL_INFRASTRUCTURE"
    AUTHORIZED_CLIENT = "AUTHORIZED_CLIENT"
    UNKNOWN_TARGET = "UNKNOWN_TARGET"


class Principal(BaseModel):
    principal_id: str = Field(..., min_length=1)
    principal_type: PrincipalType
    permissions: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    delegated_from: Optional[str] = None
    delegation_depth: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("principal_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Principal ID cannot be empty.")
        return v.strip()


class CyberAuthorizationContext(BaseModel):
    target_identifier: str = Field(..., min_length=1)
    target_type: str = Field(default="host")
    authorization_owner: str = Field(..., min_length=1)
    allowed_operations: List[str] = Field(default_factory=list)
    permitted_scope: str = Field(..., min_length=1)
    scope_category: CyberScopeCategory = CyberScopeCategory.UNKNOWN_TARGET
    scope_expiration: Optional[float] = None
    authorization_evidence_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuthorizationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")
    principal: Principal
    action: str = Field(..., min_length=1)
    resource: str = Field(..., min_length=1)
    requested_scope: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:12]}")
    requested_risk_level: Optional[RiskLevel] = None
    user_approved: bool = False
    approval_id: Optional[str] = None
    cyber_context: Optional[CyberAuthorizationContext] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:12]}")
    principal_id: str
    principal_type: PrincipalType
    action: str
    resource: str
    requested_scope: Optional[str] = None
    effective_risk: RiskLevel
    decision: PolicyDecisionType
    allowed: bool
    requires_user_approval: bool = False
    reason_code: str
    reason: str
    applicable_policies: List[str] = Field(default_factory=list)
    required_approval_id: Optional[str] = None
    correlation_id: str
    evaluation_timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"appr-{uuid.uuid4().hex[:12]}")
    principal_id: str = Field(..., min_length=1)
    principal_type: PrincipalType = PrincipalType.USER
    requested_action: str = Field(..., min_length=1)
    target_resource: str = Field(..., min_length=1)
    exact_scope: str = Field(..., min_length=1)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reason: str = Field(default="Approval required", min_length=1)
    task_id: Optional[str] = None

    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:12]}")
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: Optional[str] = None
    decision_timestamp: Optional[float] = None
    decided_at: Optional[float] = None
    cancelled_at: Optional[float] = None
    decision_reason: Optional[str] = None
    consumed_at: Optional[float] = None
    consumed_by_task_id: Optional[str] = None
    operation_fingerprint: Optional[str] = None
    request_fingerprint: Optional[str] = None
    policy_version: Optional[str] = "1.0.0"
    version: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def requester_id(self) -> str:
        return self.principal_id

    @property
    def action_type(self) -> str:
        return self.requested_action

    @property
    def resource_type(self) -> str:
        return self.target_resource

    @property
    def description(self) -> str:
        return self.reason

    @property
    def approval_scope(self) -> str:
        return self.exact_scope

    @property
    def requested_at(self) -> float:
        return self.created_at


class ApprovalDecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"decrec-{uuid.uuid4().hex[:12]}")
    approval_id: str = Field(..., min_length=1)
    approver_id: str = Field(..., min_length=1)
    decision: ApprovalStatus
    decision_reason: Optional[str] = None
    decided_at: float = Field(default_factory=time.time)
    version_at_decision: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApprovalHistoryEntry(BaseModel):
    history_id: str = Field(default_factory=lambda: f"hist-{uuid.uuid4().hex[:12]}")
    approval_id: str = Field(..., min_length=1)
    previous_status: Optional[ApprovalStatus] = None
    new_status: ApprovalStatus
    transition_reason: str = Field(..., min_length=1)
    actor_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScopedApproval(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"scop-{uuid.uuid4().hex[:12]}")
    principal_id: str = Field(..., min_length=1)
    principal_type_class: Optional[str] = None
    task_id: Optional[str] = None
    allowed_actions: List[str] = Field(default_factory=list)
    allowed_resources: List[str] = Field(default_factory=list)
    max_risk_level: RiskLevel = RiskLevel.MEDIUM
    expires_at: float
    delegation_permitted: bool = False
    max_uses: Optional[int] = None
    used_count: int = Field(default=0, ge=0)
    created_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

