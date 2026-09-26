"""
Task Data Contracts, Models, and Events for JARVIS Core (Batch 6).
"""

import json
import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from jarvis.core.enums import TaskStatus, TaskPriority, EventPriority
from jarvis.core.events.contracts import Event
from jarvis.core.logging import redact_sensitive_data


class TaskRecord(BaseModel):
    """
    Authoritative Persistent Task Record Model.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:12]}")
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=4096)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cancelled_at: Optional[float] = None
    failed_at: Optional[float] = None
    owner: str = Field(default="USER", max_length=64)
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:8]}")
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Task title cannot be empty or whitespace.")
        return redact_sensitive_data(v.strip())

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        try:
            serialized = json.dumps(v)
            if len(serialized) > 65536:  # 64KB limit
                raise ValueError("Task metadata payload size exceeds 64KB limit.")
        except (TypeError, OverflowError) as exc:
            raise ValueError(f"Metadata is not JSON serializable: {str(exc)}")
        return v

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()


class AwaitableList(list):
    """List subclass that can be awaited in async contexts."""

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()


class TaskDependency(BaseModel):
    """
    Task Dependency Relationship Contract.
    """

    task_id: str = Field(..., min_length=1)
    dependency_task_id: str = Field(..., min_length=1)
    dependency_type: str = Field(default="REQUIRED")
    created_at: float = Field(default_factory=time.time)

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()


class TaskHistoryEntry(BaseModel):
    """
    Task State Audit History Entry Contract.
    """

    history_id: str = Field(default_factory=lambda: f"hist-{uuid.uuid4().hex[:8]}")
    task_id: str = Field(..., min_length=1)
    from_status: str = Field(...)
    to_status: str = Field(...)
    timestamp: float = Field(default_factory=time.time)
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()


# ============================================================================
# TASK TYPED EVENTS (BATCH 5 INTEGRATION)
# ============================================================================


class TaskCreatedEvent(Event):
    event_type: str = "TaskCreated"


class TaskReadyEvent(Event):
    event_type: str = "TaskReady"


class TaskStartedEvent(Event):
    event_type: str = "TaskStarted"


class TaskPausedEvent(Event):
    event_type: str = "TaskPaused"


class TaskResumedEvent(Event):
    event_type: str = "TaskResumed"


class TaskCompletedEvent(Event):
    event_type: str = "TaskCompleted"


class TaskFailedEvent(Event):
    event_type: str = "TaskFailed"
    priority: EventPriority = EventPriority.HIGH


class TaskCancelledEvent(Event):
    event_type: str = "TaskCancelled"


class TaskBlockedEvent(Event):
    event_type: str = "TaskBlocked"


class TaskUpdatedEvent(Event):
    event_type: str = "TaskUpdated"
