"""
PolicyDecision, Permission, and Approval Contract Definitions (Section 18 & Section 19).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import PolicyDecisionType, RiskLevel, ApprovalStatus

class PermissionContract(BaseModel):
    name: str = Field(..., min_length=1)
    scope: str = Field(default="workspace")
    description: Optional[str] = None

class PolicyDecisionContract(BaseModel):
    action: str = Field(..., min_length=1)
    decision: PolicyDecisionType = PolicyDecisionType.DENY
    reason: str = Field(..., min_length=1)
    required_approval: bool = False
    required_authentication: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ApprovalContract(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"appr-{uuid.uuid4().hex[:12]}")
    task_id: str
    requested_action: str = Field(..., min_length=1)
    requested_by: str = Field(default="system")
    approved_by: Optional[str] = None
    scope: str = Field(default="task_scope")
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("approval_id", "task_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v
