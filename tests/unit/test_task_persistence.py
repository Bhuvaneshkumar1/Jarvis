"""
Integration & Restart Recovery Tests for Task Repository & Recovery Service (Batch 17).
"""

import os
import pytest
import tempfile
import asyncio

from jarvis.core.enums import TaskStatus, TaskPriority
from jarvis.core.tasks import (
    TaskManager,
    TaskRepository,
    TaskDuplicateIdempotencyError,
    TaskDependencyError,
)
from jarvis.core.runtime.context import RuntimeContext


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield os.path.join(tmp_dir, "test_task_repo.db")


def test_task_creation_retrieval_and_idempotency(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    mgr = TaskManager(repository=repo, db_path=temp_db_path)

    # 1. Create task
    t1 = mgr.create_task(
        title="Build Release Bundle",
        description="Compile production bundle",
        priority=TaskPriority.HIGH,
        idempotency_key="idemp-100",
    )
    assert t1.task_id.startswith("task-")
    assert t1.status in (TaskStatus.PENDING, TaskStatus.READY)

    # 2. Identical submission with same idempotency key returns original task
    t1_dup = mgr.create_task(
        title="Build Release Bundle",
        priority=TaskPriority.HIGH,
        idempotency_key="idemp-100",
    )
    assert t1_dup.task_id == t1.task_id

    # 3. Conflicting submission with same idempotency key MUST raise error
    with pytest.raises(TaskDuplicateIdempotencyError):
        mgr.create_task(
            title="Conflicting Title",
            idempotency_key="idemp-100",
        )


def test_state_transition_atomicity_and_history(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    mgr = TaskManager(repository=repo, db_path=temp_db_path)

    task = mgr.create_task(title="Deploy Pipeline")

    # Transitions
    t_queued = mgr.transition_task(task.task_id, TaskStatus.QUEUED, reason="Enqueued")
    assert t_queued.status == TaskStatus.QUEUED
    assert t_queued.version in (2, 3)

    t_ready = mgr.transition_task(task.task_id, TaskStatus.READY, reason="Ready")
    assert t_ready.status == TaskStatus.READY
    assert t_ready.version in (3, 4)

    t_running = mgr.transition_task(task.task_id, TaskStatus.RUNNING, reason="Started")
    assert t_running.status == TaskStatus.RUNNING
    assert t_running.started_at is not None

    t_completed = mgr.transition_task(task.task_id, TaskStatus.COMPLETED, reason="Done")
    assert t_completed.status == TaskStatus.COMPLETED
    assert t_completed.completed_at is not None

    # Verify history
    history = mgr.get_task_history(task.task_id)
    assert len(history) in (5, 6)


def test_task_dependencies_and_readiness_propagation(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    mgr = TaskManager(repository=repo, db_path=temp_db_path)

    parent_task = mgr.create_task(title="Build Artifact")
    child_task = mgr.create_task(title="Deploy Artifact")

    # Add dependency
    mgr.add_dependency(child_task.task_id, parent_task.task_id)

    # Self-dependency & Circular dependency prevention
    with pytest.raises(TaskDependencyError):
        mgr.add_dependency(parent_task.task_id, parent_task.task_id)

    with pytest.raises(TaskDependencyError):
        mgr.add_dependency(parent_task.task_id, child_task.task_id)

    # Completing parent propagates readiness to child task
    mgr.transition_task(parent_task.task_id, TaskStatus.QUEUED, "Queued")
    mgr.transition_task(parent_task.task_id, TaskStatus.READY, "Ready")
    mgr.transition_task(parent_task.task_id, TaskStatus.RUNNING, "Started")
    mgr.transition_task(parent_task.task_id, TaskStatus.COMPLETED, "Finished")

    child_fetched = mgr.get_task(child_task.task_id)
    assert child_fetched.status == TaskStatus.READY


def test_restart_recovery_of_interrupted_tasks(temp_db_path):
    # Session 1: Create running and cancelling tasks, then simulate process restart
    repo1 = TaskRepository(db_path=temp_db_path)
    mgr1 = TaskManager(repository=repo1, db_path=temp_db_path)

    t_running = mgr1.create_task(title="Long Running Job", max_attempts=3)
    mgr1.transition_task(t_running.task_id, TaskStatus.QUEUED, "Queued")
    mgr1.transition_task(t_running.task_id, TaskStatus.READY, "Ready")
    mgr1.transition_task(t_running.task_id, TaskStatus.RUNNING, "Started")

    t_cancelling = mgr1.create_task(title="Cancelling Job")
    mgr1.transition_task(t_cancelling.task_id, TaskStatus.QUEUED, "Queued")
    mgr1.transition_task(t_cancelling.task_id, TaskStatus.READY, "Ready")
    mgr1.transition_task(t_cancelling.task_id, TaskStatus.RUNNING, "Started")
    mgr1.transition_task(t_cancelling.task_id, TaskStatus.CANCELLING, "Requested cancel")

    # Session 2: Simulate restart by instantiating new repo and running recovery
    repo2 = TaskRepository(db_path=temp_db_path)
    mgr2 = TaskManager(repository=repo2, db_path=temp_db_path)
    asyncio.run(mgr2.initialize(RuntimeContext(environment="testing")))
    asyncio.run(mgr2.start())

    # Verify t_running transitioned to RETRY_PENDING
    recovered_running = mgr2.get_task(t_running.task_id)
    assert recovered_running.status == TaskStatus.RETRY_PENDING

    # Verify t_cancelling transitioned to CANCELLED
    recovered_cancelling = mgr2.get_task(t_cancelling.task_id)
    assert recovered_cancelling.status == TaskStatus.CANCELLED

    asyncio.run(mgr2.stop())
