"""
Unit Tests for Task State Machine, Validation & Idempotency (Batch 17).
"""

import pytest

from jarvis.core.enums import TaskStatus, TaskPriority
from jarvis.core.tasks.contracts import TaskRecord, TaskType
from jarvis.core.tasks.state_machine import TaskStateMachine
from jarvis.core.tasks.exceptions import TaskInvalidStateTransitionError


def test_task_record_defaults_and_validation():
    task = TaskRecord(title="Sample Task", owner="USER")
    assert task.task_id.startswith("task-")
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.MEDIUM
    assert task.task_type == TaskType.GENERAL
    assert task.version == 1

    with pytest.raises(ValueError):
        TaskRecord(title="   ")


def test_task_state_machine_valid_transitions():
    # Valid transition paths
    TaskStateMachine.validate_transition("task-1", TaskStatus.CREATED, TaskStatus.QUEUED)
    TaskStateMachine.validate_transition("task-1", TaskStatus.QUEUED, TaskStatus.READY)
    TaskStateMachine.validate_transition("task-1", TaskStatus.READY, TaskStatus.RUNNING)
    TaskStateMachine.validate_transition("task-1", TaskStatus.RUNNING, TaskStatus.COMPLETED)
    TaskStateMachine.validate_transition("task-1", TaskStatus.RUNNING, TaskStatus.PAUSED)
    TaskStateMachine.validate_transition("task-1", TaskStatus.PAUSED, TaskStatus.RUNNING)
    TaskStateMachine.validate_transition("task-1", TaskStatus.RUNNING, TaskStatus.FAILED)
    TaskStateMachine.validate_transition("task-1", TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL)
    TaskStateMachine.validate_transition("task-1", TaskStatus.WAITING_APPROVAL, TaskStatus.READY)
    TaskStateMachine.validate_transition("task-1", TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED)


def test_task_state_machine_invalid_transition_rejection():
    # Illegal transition attempts MUST raise TaskInvalidStateTransitionError
    with pytest.raises(TaskInvalidStateTransitionError):
        TaskStateMachine.validate_transition("task-1", TaskStatus.COMPLETED, TaskStatus.RUNNING)

    with pytest.raises(TaskInvalidStateTransitionError):
        TaskStateMachine.validate_transition("task-1", TaskStatus.CANCELLED, TaskStatus.READY)

    with pytest.raises(TaskInvalidStateTransitionError):
        TaskStateMachine.validate_transition("task-1", TaskStatus.CREATED, TaskStatus.COMPLETED)
