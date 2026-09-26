"""
Orchestration Command Contracts and Result Models for JARVIS Core (Batch 7).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from jarvis.core.enums import TaskStatus, TaskPriority


class Command(BaseModel):
    """
    Authoritative Base Command Contract for Orchestrator Operations.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    command_id: str = Field(default_factory=lambda: f"cmd-{uuid.uuid4().hex[:12]}")
    command_type: str = Field(..., min_length=1)
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:8]}")
    causation_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None

    @field_validator("command_id", "command_type")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Command identifier and type cannot be empty.")
        return v.strip()

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()


class CreateTaskCommand(Command):
    """Command to create and persist a new task."""

    command_type: str = Field(default="CreateTask")
    title: Optional[str] = None
    description: Optional[str] = None
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    owner: str = Field(default="USER")
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StartTaskCommand(Command):
    """Command to coordinate transition of a READY task to RUNNING."""

    command_type: str = Field(default="StartTask")
    task_id: str = Field(..., min_length=1)


class PauseTaskCommand(Command):
    """Command to pause a RUNNING task."""

    command_type: str = Field(default="PauseTask")
    task_id: str = Field(..., min_length=1)
    reason: Optional[str] = None


class ResumeTaskCommand(Command):
    """Command to resume a PAUSED task."""

    command_type: str = Field(default="ResumeTask")
    task_id: str = Field(..., min_length=1)


class CancelTaskCommand(Command):
    """Command to cancel an active task."""

    command_type: str = Field(default="CancelTask")
    task_id: str = Field(..., min_length=1)
    reason: Optional[str] = None


class GetTaskCommand(Command):
    """Command to retrieve a task by ID."""

    command_type: str = Field(default="GetTask")
    task_id: str = Field(..., min_length=1)


class ListTasksCommand(Command):
    """Command to list and filter tasks."""

    command_type: str = Field(default="ListTasks")
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    owner: Optional[str] = None
    parent_task_id: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ShutdownApplicationCommand(Command):
    """Command to initiate graceful application runtime shutdown."""

    command_type: str = Field(default="ShutdownApplication")
    reason: str = Field(default="Shutdown requested via orchestrator command")


class GetRuntimeStatusCommand(Command):
    """Command to retrieve runtime status."""

    command_type: str = Field(default="GetRuntimeStatus")


class CommandResult(BaseModel):
    """
    Authoritative Command Execution Result Contract.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    command_id: str
    correlation_id: str
    task_id: Optional[str] = None
    status: str
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)

    def __await__(self):
        async def _res():
            return self

        return _res().__await__()
