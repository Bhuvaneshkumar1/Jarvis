"""
Authoritative Task Lifecycle State Machine for JARVIS (Batch 17).
Defines explicit valid state transitions and rejects illegal status changes.
"""

from typing import Set, Dict
from jarvis.core.enums import TaskStatus
from jarvis.core.tasks.exceptions import TaskInvalidStateTransitionError

# Terminal states from which tasks cannot transition without retry
TERMINAL_STATES: Set[TaskStatus] = {
    TaskStatus.COMPLETED,
    TaskStatus.CANCELLED,
    TaskStatus.FAILED,
    TaskStatus.BLOCKED,
}

# Permitted state transition map
PERMITTED_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED},
    TaskStatus.PENDING: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_DEPENDENCY,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.CANCELLED,
    },
    TaskStatus.QUEUED: {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.WAITING_DEPENDENCY, TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED},
    TaskStatus.READY: {
        TaskStatus.QUEUED,
        TaskStatus.PENDING,
        TaskStatus.RUNNING,
        TaskStatus.PAUSED,
        TaskStatus.WAITING_DEPENDENCY,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.PAUSED,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.WAITING_DEPENDENCY,
        TaskStatus.RETRY_PENDING,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
        TaskStatus.VERIFYING,
    },
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.PAUSED: {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_DEPENDENCY: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
    TaskStatus.RETRY_PENDING: {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.INTERRUPTED: {TaskStatus.RETRY_PENDING, TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.CANCELLING: {TaskStatus.CANCELLED, TaskStatus.FAILED},
    # Self-transitions to same status are allowed
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.FAILED: {TaskStatus.RETRY_PENDING},  # Allowed only for retry
    TaskStatus.BLOCKED: {TaskStatus.READY},  # Allowed if unblocked
}


class TaskStateMachine:
    """
    Authoritative Task State Machine enforcing lifecycle transition invariants.
    """

    @staticmethod
    def is_valid_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Check if transition from_status -> to_status is valid."""
        if from_status == to_status:
            return True
        allowed = PERMITTED_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    @staticmethod
    def validate_transition(task_id: str, from_status: TaskStatus, to_status: TaskStatus) -> None:
        """
        Validates state transition.
        Raises TaskInvalidStateTransitionError if transition is illegal.
        """
        if from_status == to_status:
            return

        if from_status in TERMINAL_STATES and to_status not in PERMITTED_TRANSITIONS.get(from_status, set()):
            raise TaskInvalidStateTransitionError(f"Cannot transition task '{task_id}' from terminal state '{from_status.value}' to '{to_status.value}'.")

        if not TaskStateMachine.is_valid_transition(from_status, to_status):
            raise TaskInvalidStateTransitionError(f"Invalid state transition for task '{task_id}': '{from_status.value}' -> '{to_status.value}'.")
