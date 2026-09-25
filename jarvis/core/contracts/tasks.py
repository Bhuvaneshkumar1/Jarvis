"""
Task and TaskStep Contract Definitions (Section 8 & Section 9).
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import TaskStatus, TaskPriority, RequestSource, ApprovalStatus, VerificationResultStatus, StepStatus

class TaskStepContract(BaseModel):
    step_id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:12]}")
    task_id: str
    sequence: int = Field(default=1, ge=1)
    description: str = Field(..., min_length=1)
    dependencies: List[str] = Field(default_factory=list)
    assigned_agent_id: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    required_permission: Optional[str] = None
    result: Optional[Any] = None
    verification_id: Optional[str] = None

    @field_validator("step_id", "task_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v

class TaskContract(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:12]}")
    parent_task_id: Optional[str] = None
    description: str = Field(..., min_length=1)
    objective: Optional[str] = None
    status: TaskStatus = TaskStatus.CREATED
    priority: TaskPriority = TaskPriority.MEDIUM
    source: RequestSource = RequestSource.LOCAL_UI
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    deadline: Optional[float] = None
    assigned_agent_id: Optional[str] = None
    approval_state: ApprovalStatus = ApprovalStatus.PENDING
    verification_state: VerificationResultStatus = VerificationResultStatus.NOT_VERIFIED
    retry_count: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task_id cannot be empty or whitespace.")
        return v
