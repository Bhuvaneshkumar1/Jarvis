"""
Unit, Negative, Lifecycle, and Integration Tests for JARVIS Orchestrator (Batch 7).
"""

import asyncio
import os
import pytest
import tempfile
from jarvis.core.enums import TaskPriority, RuntimeState
from jarvis.core.events import EventBus
from jarvis.core.tasks import TaskManager, TaskRepository
from jarvis.core.runtime import JarvisApplication
from jarvis.core.orchestration import (
    Orchestrator,
    Command,
    CreateTaskCommand,
    StartTaskCommand,
    CancelTaskCommand,
    GetTaskCommand,
    GetRuntimeStatusCommand,
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
async def test_orchestrator_command_execution_and_task_creation(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    orchestrator = Orchestrator(task_manager=tm)
    await orchestrator.start()

    # 1. Create Task via Command
    cmd_create = CreateTaskCommand(
        title="Orchestrated Task",
        description="Task created via Orchestrator command",
        priority=TaskPriority.HIGH,
        owner="USER",
        metadata={"category": "orchestration"},
    )
    res_create = orchestrator.execute_command(cmd_create)
    assert res_create.success is True
    assert res_create.task_id.startswith("task-")
    assert res_create.status == "READY"  # No deps -> READY

    task_id = res_create.task_id

    # 2. Get Task via Command
    cmd_get = GetTaskCommand(task_id=task_id)
    res_get = orchestrator.execute_command(cmd_get)
    assert res_get.success is True
    assert res_get.task_id == task_id
    assert res_get.data["title"] == "Orchestrated Task"

    # 3. Start Task via Command
    cmd_start = StartTaskCommand(task_id=task_id)
    res_start = orchestrator.execute_command(cmd_start)
    assert res_start.success is True
    assert res_start.status == "RUNNING"

    # 4. Cancel Task via Command
    cmd_cancel = CancelTaskCommand(task_id=task_id, reason="User cancelled execution")
    res_cancel = orchestrator.execute_command(cmd_cancel)
    assert res_cancel.success is True
    assert res_cancel.status == "CANCELLED"

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_idempotency(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    orchestrator = Orchestrator(task_manager=tm)
    await orchestrator.start()

    cmd = CreateTaskCommand(
        title="Idempotent Task",
        idempotency_key="idempotency-key-12345",
    )

    res1 = orchestrator.execute_command(cmd)
    assert res1.success is True
    task_id_1 = res1.task_id

    # Execute duplicate command with same idempotency key
    res2 = orchestrator.execute_command(cmd)
    assert res2.success is True
    assert res2.task_id == task_id_1
    assert res2.command_id == res1.command_id

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_invalid_command_negative_tests(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    orchestrator = Orchestrator(task_manager=tm)
    await orchestrator.start()

    # 1. Non-existent task
    cmd_get = GetTaskCommand(task_id="non_existent_task_999")
    res_get = orchestrator.execute_command(cmd_get)
    assert res_get.success is False
    assert res_get.error_code == "TASK_NOT_FOUND"

    # 2. Invalid command type
    cmd_invalid = Command(command_type="UnrecognizedCommandType")
    res_invalid = orchestrator.execute_command(cmd_invalid)
    assert res_invalid.success is False
    assert res_invalid.error_code == "COMMAND_EXECUTION_ERROR"

    # 3. Invalid command when orchestrator STOPPED
    await orchestrator.stop()
    cmd_create = CreateTaskCommand(title="Task while stopped")
    res_stopped = orchestrator.execute_command(cmd_create)
    assert res_stopped.success is False
    assert res_stopped.error_code == "ORCHESTRATOR_NOT_RUNNING"


@pytest.mark.asyncio
async def test_orchestrator_event_reactions(temp_db_path):
    event_bus = EventBus()
    await event_bus.start()
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo, event_bus=event_bus)
    await tm.start()

    orchestrator = Orchestrator(event_bus=event_bus, task_manager=tm)
    await orchestrator.start()

    # Create task -> triggers TaskCreated & TaskReady events -> Orchestrator receives event
    cmd = CreateTaskCommand(title="Event Reaction Task")
    res = orchestrator.execute_command(cmd)
    assert res.success is True

    await asyncio.sleep(0.1)  # Allow async event bus dispatch

    await orchestrator.stop()
    await tm.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_orchestrator_runtime_kernel_integration():
    app = JarvisApplication()
    assert app.registry.has("EventBus")
    assert app.registry.has("TaskManager")
    assert app.registry.has("Orchestrator")

    # Topological order: EventBus -> TaskManager -> Orchestrator
    init_order = [c.name for c in app.registry.get_initialization_order()]
    assert init_order.index("EventBus") < init_order.index("TaskManager")
    assert init_order.index("TaskManager") < init_order.index("Orchestrator")

    await app.start()
    assert app.orchestrator.state == RuntimeState.RUNNING

    status = app.get_status()
    assert status["state"] == "RUNNING"
    assert status["total_components"] == 3

    await app.shutdown("Test complete")
    assert app.orchestrator.state == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_core_flow(temp_db_path):
    event_bus = EventBus()
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo, event_bus=event_bus)
    orchestrator = Orchestrator(event_bus=event_bus, task_manager=tm)

    app = JarvisApplication(event_bus=event_bus, task_manager=tm, orchestrator=orchestrator)
    await app.start()

    # 1. Create task
    c1 = CreateTaskCommand(title="End to End Core Task")
    r1 = orchestrator.execute_command(c1)
    assert r1.success is True
    task_id = r1.task_id

    # 2. Start task
    c2 = StartTaskCommand(task_id=task_id)
    r2 = orchestrator.execute_command(c2)
    assert r2.success is True
    assert r2.status == "RUNNING"

    # 3. Cancel task
    c3 = CancelTaskCommand(task_id=task_id, reason="End of test flow")
    r3 = orchestrator.execute_command(c3)
    assert r3.success is True
    assert r3.status == "CANCELLED"

    # 4. Get runtime status
    c4 = GetRuntimeStatusCommand()
    r4 = orchestrator.execute_command(c4)
    assert r4.success is True
    assert r4.data["orchestrator_state"] == "RUNNING"

    await app.shutdown("E2E complete")


@pytest.mark.asyncio
async def test_orchestrator_persistent_restart_flow(temp_db_path):
    # Step 1: Start system, create task
    repo1 = TaskRepository(db_path=temp_db_path)
    tm1 = TaskManager(repository=repo1)
    orc1 = Orchestrator(task_manager=tm1)
    await tm1.start()
    await orc1.start()

    r1 = orc1.execute_command(CreateTaskCommand(title="Persistent Restart Task"))
    task_id = r1.task_id
    assert r1.success is True

    await orc1.stop()
    await tm1.stop()

    # Step 2: Restart system with same SQLite file
    repo2 = TaskRepository(db_path=temp_db_path)
    tm2 = TaskManager(repository=repo2)
    orc2 = Orchestrator(task_manager=tm2)
    await tm2.start()
    await orc2.start()

    # Query task via Orchestrator
    r2 = orc2.execute_command(GetTaskCommand(task_id=task_id))
    assert r2.success is True
    assert r2.data["title"] == "Persistent Restart Task"

    await orc2.stop()
    await tm2.stop()
