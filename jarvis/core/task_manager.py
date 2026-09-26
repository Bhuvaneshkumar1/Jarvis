"""
Legacy Re-export module for TaskManager (Batch 6 Consolidation).
All authoritative task management functionality resides in jarvis.core.tasks.
"""

from jarvis.core.enums import TaskStatus
from jarvis.core.tasks import TaskManager, TaskRecord, TaskRepository


class LegacyTaskState:
    PENDING = TaskStatus.PENDING
    READY = TaskStatus.READY
    RUNNING = TaskStatus.RUNNING
    PAUSED = TaskStatus.PAUSED
    COMPLETED = TaskStatus.COMPLETED
    FAILED = TaskStatus.FAILED
    CANCELLED = TaskStatus.CANCELLED
    BLOCKED = TaskStatus.BLOCKED
    INTERRUPTED = TaskStatus.INTERRUPTED
    # Legacy Orchestrator pipeline aliases
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    ROLLED_BACK = "ROLLED_BACK"
    POLICY_DENIED = "POLICY_DENIED"


TaskState = LegacyTaskState

__all__ = ["TaskManager", "TaskRecord", "TaskRepository", "TaskState", "LegacyTaskState"]
