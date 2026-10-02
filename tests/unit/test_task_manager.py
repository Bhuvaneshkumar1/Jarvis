"""
Unit, Negative, Persistence, and Recovery Tests for JARVIS Task Manager (Batch 6).
"""

import asyncio
import os
import pytest
import tempfile
from typing import List
from jarvis.core.enums import TaskStatus, TaskPriority, RuntimeState
from jarvis.core.events import EventBus, Event
from jarvis.core.tasks import (
    TaskManager,
    TaskRepository,
)
from jarvis.core.runtime import JarvisApplication
from jarvis.core.exceptions import (
    TaskNotFoundError,
    InvalidTaskTransitionError,
    TaskVersionConflictError,
    TaskDependencyError,
)


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_task_creation_and_persistence(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    task = await tm.create_task(
        title="Implement Task Manager",
        description="Build persistent state engine",
        priority=TaskPriority.HIGH,
        owner="USER",
        metadata={"category": "core"},
    )

    assert task.task_id.startswith("task-")
    assert task.title == "Implement Task Manager"
    # Initial creation state
    assert task.status in (TaskStatus.PENDING, TaskStatus.READY)
    assert task.version in (1, 2)

    fetched = await tm.get_task(task.task_id)
    assert fetched.task_id == task.task_id
    assert fetched.metadata["category"] == "core"

    await tm.stop()


@pytest.mark.asyncio
async def test_task_state_transitions(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    task = await tm.create_task(title="Transition Test Task")
    assert task.status == TaskStatus.READY

    # READY -> RUNNING
    running_task = await tm.transition_task(task.task_id, TaskStatus.RUNNING)
    assert running_task.status == TaskStatus.RUNNING
    assert running_task.started_at is not None

    # RUNNING -> COMPLETED
    completed_task = await tm.transition_task(running_task.task_id, TaskStatus.COMPLETED)
    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.completed_at is not None

    # Verify history
    history = await tm.get_history(task.task_id)
    statuses = [h.to_status for h in history]
    assert "PENDING" in statuses
    assert "READY" in statuses
    assert "RUNNING" in statuses
    assert "COMPLETED" in statuses

    await tm.stop()


@pytest.mark.asyncio
async def test_invalid_task_transition_negative_test(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    task = await tm.create_task(title="Invalid Transition Task")
    await tm.transition_task(task.task_id, TaskStatus.RUNNING)
    await tm.transition_task(task.task_id, TaskStatus.COMPLETED)

    # COMPLETED -> RUNNING (Terminal transition must fail)
    with pytest.raises(InvalidTaskTransitionError):
        await tm.transition_task(task.task_id, TaskStatus.RUNNING)

    await tm.stop()


@pytest.mark.asyncio
async def test_optimistic_locking_version_conflict(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    task = await tm.create_task(title="Version Conflict Task")
    v_orig = task.version

    # First update succeeds
    await tm.transition_task(task.task_id, TaskStatus.RUNNING, expected_version=v_orig)

    # Second update using stale version v_orig should raise TaskVersionConflictError
    with pytest.raises(TaskVersionConflictError):
        await tm.transition_task(task.task_id, TaskStatus.COMPLETED, expected_version=v_orig)

    await tm.stop()


@pytest.mark.asyncio
async def test_task_dependencies_and_readiness_propagation(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    t1 = await tm.create_task(title="Prerequisite Task A")
    t2 = await tm.create_task(title="Dependent Task B")

    # Add dependency: B depends on A
    await tm.add_dependency(t2.task_id, t1.task_id)

    # B should be WAITING_DEPENDENCY / BLOCKED while A is READY/RUNNING
    t2_blocked = await tm.get_task(t2.task_id)
    assert t2_blocked.status in (TaskStatus.BLOCKED, TaskStatus.WAITING_DEPENDENCY)

    # Run and complete A
    await tm.transition_task(t1.task_id, TaskStatus.RUNNING)
    await tm.transition_task(t1.task_id, TaskStatus.COMPLETED)

    # Check B again: Readiness propagation should have transitioned B to READY!
    t2_ready = await tm.get_task(t2.task_id)
    assert t2_ready.status == TaskStatus.READY

    await tm.stop()


@pytest.mark.asyncio
async def test_self_and_circular_dependency_negative_tests(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    t1 = await tm.create_task(title="Task 1")
    t2 = await tm.create_task(title="Task 2")
    t3 = await tm.create_task(title="Task 3")

    # Self dependency
    with pytest.raises(TaskDependencyError):
        await tm.add_dependency(t1.task_id, t1.task_id)

    # Chain: T2 depends on T1, T3 depends on T2
    await tm.add_dependency(t2.task_id, t1.task_id)
    await tm.add_dependency(t3.task_id, t2.task_id)

    # Circular dependency: T1 depends on T3 (T1 -> T3 -> T2 -> T1)
    with pytest.raises(TaskDependencyError):
        await tm.add_dependency(t1.task_id, t3.task_id)

    await tm.stop()


@pytest.mark.asyncio
async def test_restart_recovery_simulation(temp_db_path):
    # Step 1: Initialize DB and create task running
    repo1 = TaskRepository(db_path=temp_db_path)
    tm1 = TaskManager(repository=repo1)
    await tm1.start()

    task1 = await tm1.create_task(title="Interrupted Task")
    await tm1.transition_task(task1.task_id, TaskStatus.RUNNING)

    # Simulate unexpected process crash without calling tm1.stop()
    del tm1
    del repo1

    # Step 2: Restart process with same persistent SQLite file
    repo2 = TaskRepository(db_path=temp_db_path)
    tm2 = TaskManager(repository=repo2)

    # Startup recovery runs during tm2.start()
    await tm2.start()

    recovered_task = await tm2.get_task(task1.task_id)
    assert recovered_task.status in (TaskStatus.RETRY_PENDING, TaskStatus.INTERRUPTED)

    history = await tm2.get_history(task1.task_id)
    assert history[-1].to_status in ("RETRY_PENDING", "INTERRUPTED")
    assert "Process restart recovery" in history[-1].reason

    await tm2.stop()


@pytest.mark.asyncio
async def test_event_bus_task_manager_integration(temp_db_path):
    event_bus = EventBus()
    await event_bus.start()

    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo, event_bus=event_bus)
    await tm.start()

    events_captured: List[str] = []

    async def task_event_listener(evt: Event) -> None:
        events_captured.append(evt.event_type)

    event_bus.subscribe("*", task_event_listener)

    task = await tm.create_task(title="Event Test Task")
    await tm.transition_task(task.task_id, TaskStatus.RUNNING)
    await tm.transition_task(task.task_id, TaskStatus.COMPLETED)

    await asyncio.sleep(0.1)

    assert "TaskCreated" in events_captured
    assert "TaskReady" in events_captured
    assert "TaskStarted" in events_captured
    assert "TaskCompleted" in events_captured

    await tm.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_input_validation_and_size_limits_negative_tests(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    # Empty title
    with pytest.raises(ValueError):
        await tm.create_task(title="")

    # Missing parent task
    with pytest.raises(TaskNotFoundError):
        await tm.create_task(title="Child Task", parent_task_id="non_existent_parent")

    # Oversized metadata (>64KB)
    huge_meta = {"data": "x" * 70000}
    with pytest.raises(ValueError):
        await tm.create_task(title="Oversized Task", metadata=huge_meta)

    await tm.stop()


@pytest.mark.asyncio
async def test_task_manager_query_and_pagination(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    await tm.start()

    for i in range(15):
        await tm.create_task(
            title=f"Paginated Task {i}",
            owner="ALICE" if i % 2 == 0 else "BOB",
            priority=TaskPriority.HIGH if i < 5 else TaskPriority.LOW,
        )

    alice_tasks = await tm.list_tasks(owner="ALICE")
    assert len(alice_tasks) == 8

    high_tasks = await tm.list_tasks(priority=TaskPriority.HIGH)
    assert len(high_tasks) == 5

    page1 = await tm.list_tasks(limit=5, offset=0)
    page2 = await tm.list_tasks(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    assert page1[0].task_id != page2[0].task_id

    await tm.stop()


@pytest.mark.asyncio
async def test_application_kernel_task_manager_integration():
    app = JarvisApplication()
    assert app.registry.has("TaskManager")

    await app.start()
    assert app.task_manager.state == RuntimeState.RUNNING

    t = await app.task_manager.create_task(title="Kernel Integrated Task")
    assert t.status == TaskStatus.READY

    await app.shutdown("Kernel integration test complete")
    assert app.task_manager.state == RuntimeState.STOPPED
