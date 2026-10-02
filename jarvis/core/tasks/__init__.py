"""
Authoritative Task Management & Persistence Subsystem for JARVIS (Batch 6 & Batch 17).
Exports TaskManager, TaskRepository, TaskStateMachine, TaskRecoveryService, TaskEventPublisher,
TaskRecord, TaskHistoryEntry, TaskDependency, TaskType, TaskQueryFilter, TaskRecoveryReport, and exceptions.
"""

from jarvis.core.tasks.contracts import (
    TaskRecord,
    TaskHistoryEntry,
    TaskDependency,
    TaskType,
    TaskQueryFilter,
    TaskRecoveryReport,
    TaskCreatedEvent,
    TaskReadyEvent,
    TaskStartedEvent,
    TaskPausedEvent,
    TaskResumedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskCancelledEvent,
    TaskBlockedEvent,
    TaskUpdatedEvent,
    TaskCancellationRequestedEvent,
    TaskRetryScheduledEvent,
    TaskRecoveryRequiredEvent,
    TaskRecoveredEvent,
    AwaitableList,
)
from jarvis.core.tasks.exceptions import (
    TaskError,
    TaskNotFoundError,
    TaskInvalidStateTransitionError,
    TaskVersionConflictError,
    TaskDependencyError,
    TaskDuplicateIdempotencyError,
    TaskAuthorizationError,
    TaskValidationError,
)
from jarvis.core.tasks.state_machine import TaskStateMachine, TERMINAL_STATES, PERMITTED_TRANSITIONS
from jarvis.core.tasks.repository import TaskRepository
from jarvis.core.tasks.recovery import TaskRecoveryService
from jarvis.core.tasks.outbox import TaskEventPublisher
from jarvis.core.tasks.manager import TaskManager

__all__ = [
    "TaskRecord",
    "TaskHistoryEntry",
    "TaskDependency",
    "TaskType",
    "TaskQueryFilter",
    "TaskRecoveryReport",
    "TaskCreatedEvent",
    "TaskReadyEvent",
    "TaskStartedEvent",
    "TaskPausedEvent",
    "TaskResumedEvent",
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "TaskCancelledEvent",
    "TaskBlockedEvent",
    "TaskUpdatedEvent",
    "TaskCancellationRequestedEvent",
    "TaskRetryScheduledEvent",
    "TaskRecoveryRequiredEvent",
    "TaskRecoveredEvent",
    "AwaitableList",
    "TaskError",
    "TaskNotFoundError",
    "TaskInvalidStateTransitionError",
    "TaskVersionConflictError",
    "TaskDependencyError",
    "TaskDuplicateIdempotencyError",
    "TaskAuthorizationError",
    "TaskValidationError",
    "TaskStateMachine",
    "TERMINAL_STATES",
    "PERMITTED_TRANSITIONS",
    "TaskRepository",
    "TaskRecoveryService",
    "TaskEventPublisher",
    "TaskManager",
]
