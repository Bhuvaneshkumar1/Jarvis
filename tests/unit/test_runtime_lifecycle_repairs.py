"""
Mandatory Tests for Application Runtime Kernel & EventBus Lifecycle Repairs (Section 4).
Covering startup, running state, graceful shutdown, concurrency, task tracking, and rollback.
"""

import asyncio
import pytest
from jarvis.core.enums import RuntimeState
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.runtime.application import JarvisApplication
from jarvis.core.events.bus import EventBus
from jarvis.core.events.contracts import Event
from jarvis.core.exceptions import (
    EventPublishError,
    ComponentStartError,
)


class MockFailingStartComponent(LifecycleComponent):
    @property
    def name(self) -> str:
        return "failing_start_comp"

    async def initialize(self, context: RuntimeContext) -> None:
        pass

    async def start(self) -> None:
        raise RuntimeError("Simulated startup failure")

    async def stop(self) -> None:
        pass


class MockSlowStartupComponent(LifecycleComponent):
    def __init__(self, name: str = "slow_comp"):
        self._name = name
        self.started = False
        self.stopped = False

    @property
    def name(self) -> str:
        return self._name

    async def initialize(self, context: RuntimeContext) -> None:
        pass

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_app_normal_startup():
    """Mandatory Test 1: Normal application startup."""
    app = JarvisApplication()
    await app.start()
    assert app.state == RuntimeState.RUNNING
    await app.shutdown("Test completed")


@pytest.mark.asyncio
async def test_app_remains_active_when_running():
    """Mandatory Test 2: Runtime remaining active after successful startup."""
    app = JarvisApplication()
    await app.start()
    assert app.state == RuntimeState.RUNNING
    assert not app.context.cancellation_event.is_set()
    await app.shutdown("Test completed")


@pytest.mark.asyncio
async def test_app_graceful_shutdown():
    """Mandatory Test 3: Graceful shutdown."""
    app = JarvisApplication()
    await app.start()
    await app.shutdown("Graceful test shutdown")
    assert app.state == RuntimeState.STOPPED
    assert app.shutdown_reason == "Graceful test shutdown"


@pytest.mark.asyncio
async def test_concurrent_publish_and_shutdown():
    """Mandatory Test 4: Concurrent event publication and shutdown."""
    bus = EventBus()
    await bus.start()

    async def _publish_loop():
        for i in range(20):
            try:
                await bus.publish(Event(event_type=f"TestEvent_{i}"))
            except EventPublishError:
                break
            await asyncio.sleep(0.001)

    pub_task = asyncio.create_task(_publish_loop())
    await asyncio.sleep(0.005)
    await bus.stop()
    await pub_task
    assert bus.state == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_publish_attempted_after_stopping():
    """Mandatory Test 5: Publication attempted after STOPPING."""
    bus = EventBus()
    await bus.start()
    await bus.stop()

    with pytest.raises(EventPublishError):
        await bus.publish(Event(event_type="PostShutdownEvent"))


@pytest.mark.asyncio
async def test_background_task_exception_handling():
    """Mandatory Test 6: Background task exception handling."""
    app = JarvisApplication()
    await app.start()

    async def _failing_coro():
        raise ValueError("Simulated background task failure")

    task = asyncio.create_task(_failing_coro())
    tracked_task = app._track_task(task)

    # Allow task to complete
    await asyncio.sleep(0.01)

    # Ensure task exception was retrieved cleanly by callback without raising unhandled warning
    assert tracked_task.done()
    assert isinstance(tracked_task.exception(), ValueError)

    await app.shutdown("Test cleanup")


@pytest.mark.asyncio
async def test_startup_failure_component():
    """Mandatory Test 7: Startup failure in an individual component."""
    app = JarvisApplication()
    failing_comp = MockFailingStartComponent()
    app.register_component(failing_comp)

    with pytest.raises(ComponentStartError):
        await app.start()

    assert app.state == RuntimeState.FAILED


@pytest.mark.asyncio
async def test_partial_startup_rollback():
    """Mandatory Test 8: Partial startup rollback."""
    app = JarvisApplication()
    good_comp = MockSlowStartupComponent("good_comp")
    failing_comp = MockFailingStartComponent()

    app.register_component(good_comp)
    app.register_component(failing_comp)

    with pytest.raises(ComponentStartError):
        await app.start()

    assert app.state == RuntimeState.FAILED
    assert good_comp.stopped is True


@pytest.mark.asyncio
async def test_repeated_shutdown_idempotent():
    """Mandatory Test 9: Repeated shutdown requests."""
    app = JarvisApplication()
    await app.start()
    await app.shutdown("First shutdown")
    assert app.state == RuntimeState.STOPPED

    # Second shutdown call must be idempotent and clean
    await app.shutdown("Second shutdown")
    assert app.state == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_no_pending_tasks_after_shutdown():
    """Mandatory Test 10: No pending application-owned tasks after shutdown."""
    app = JarvisApplication()
    await app.start()

    # Create dummy background task
    async def _long_task():
        await asyncio.sleep(10.0)

    task = asyncio.create_task(_long_task())
    app._track_task(task)

    await app.shutdown("Shutdown check")
    assert len([t for t in app._background_tasks if not t.done()]) == 0
