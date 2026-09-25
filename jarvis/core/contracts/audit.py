"""
AuditEvent Contract Definitions (Section 21).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import AuditSeverity


class AuditEventContract(BaseModel, frozen=True):
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    timestamp: float = Field(default_factory=time.time)
    correlation_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    component: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    result: str = Field(default="SUCCESS")
    severity: AuditSeverity = AuditSeverity.INFO
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "component", "action")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("String field cannot be empty or whitespace.")
        return v
