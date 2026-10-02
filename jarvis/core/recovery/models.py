"""
Recovery Data Models and Classification Contracts for JARVIS (Batch 19).
"""

import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class RecoveryStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    INSPECTING = "INSPECTING"
    RECOVERING = "RECOVERING"
    RECONCILING = "RECONCILING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class OperationClassification(str, Enum):
    CONFIRMED_NOT_EXECUTED = "CONFIRMED_NOT_EXECUTED"
    CONFIRMED_EXECUTED = "CONFIRMED_EXECUTED"
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"
    REQUIRES_MANUAL_INTERVENTION = "REQUIRES_MANUAL_INTERVENTION"
    INVALID_OR_INCONSISTENT = "INVALID_OR_INCONSISTENT"


class RecoveryRecord(BaseModel):
    recovery_id: str = Field(default_factory=lambda: f"rec-{uuid.uuid4().hex[:12]}")
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:12]}")
    status: RecoveryStatus = RecoveryStatus.NOT_STARTED
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    inspected_count: int = Field(default=0, ge=0)
    recovered_count: int = Field(default=0, ge=0)
    reconciled_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    manual_intervention_count: int = Field(default=0, ge=0)
    details: Dict[str, Any] = Field(default_factory=dict)


class OutboxEventRecord(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    event_type: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    status: str = Field(default="PENDING")
    created_at: float = Field(default_factory=time.time)
    dispatched_at: Optional[float] = None
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    last_error: Optional[str] = None
