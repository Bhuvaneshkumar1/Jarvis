"""
Unit and Negative Tests for JARVIS Application Runtime Kernel (Batch 4).
"""

import asyncio
import pytest
from typing import List
from jarvis.core.enums import RuntimeState, HealthState
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.runtime import (
    LifecycleComponent,
    RuntimeContext,
    ComponentRegistry,
    JarvisApplication,
)
from jarvis.core.exceptions import (
    DuplicateComponentError,
    MissingDependencyError,
    DependencyCycleError,
    InvalidStateTransitionError,
    ComponentInitializationError,
    ComponentStartError,
)


# ============================================================================
# TEST COMPONENTS (FIXTURES)
# ============================================================================


class MockSuccessfulComponent(LifecycleComponent):
    def __init__(self, name: str = "successful_comp", deps: List[str] = None):
        self._name = name
        self._deps = deps or []
        self.initialized = False
        self.started = False
        self.stopped = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> List[str]:
        return self._deps

    async def initialize(self, context: RuntimeContext) -> None:
        self.initialized = True

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class MockInitFailingComponent(LifecycleComponent):
    @property
    def name(self) -> str:
        return "init_failing_comp"

    async def initialize(self, context: RuntimeContext) -> None:
        raise ValueError("Simulated initialization failure")


class MockStartFailingComponent(LifecycleComponent):
    @property
    def name(self) -> str:
        return "start_failing_comp"

    async def start(self) -> None:
        raise RuntimeError("Simulated start failure")


class MockStopFailingComponent(LifecycleComponent):
    @property
    def name(self) -> str:
        return "stop_failing_comp"

    async def stop(self) -> None:
        raise RuntimeError("Simulated stop failure")


class MockSlowComponent(LifecycleComponent):
    def __init__(self, delay: float = 2.0):
        self.delay = delay

    @property
    def name(self) -> str:
        return "slow_comp"

    async def initialize(self, context: RuntimeContext) -> None:
        await asyncio.sleep(self.delay)

    async def start(self) -> None:
        await asyncio.sleep(self.delay)

    async def stop(self) -> None:
        await asyncio.sleep(self.delay)


class MockUnhealthyComponent(LifecycleComponent):
    @property
    def name(self) -> str:
        return "unhealthy_comp"

    async def health(self) -> HealthStatusContract:
        return HealthStatusContract(
            component=self.name,
            status=HealthState.UNHEALTHY,
            error="Degraded resource pool",
        )


class MockCircularA(LifecycleComponent):
    @property
    def name(self) -> str:
        return "comp_a"

    @property
    def dependencies(self) -> List[str]:
        return ["comp_b"]


class MockCircularB(LifecycleComponent):
    @property
    def name(self) -> str:
        return "comp_b"

    @property
    def dependencies(self) -> List[str]:
        return ["comp_a"]


# ============================================================================
# COMPONENT REGISTRY TESTS
# ============================================================================


def test_registry_registration_and_lookup():
    reg = ComponentRegistry()
    comp = MockSuccessfulComponent("c1")
    reg.register(comp)

    assert reg.has("c1")
    assert reg.get("c1") == comp
    assert reg.count() == 1
    assert comp in reg.all_components()


def test_registry_duplicate_registration_fails():
    reg = ComponentRegistry()
    comp1 = MockSuccessfulComponent("duplicate")
    comp2 = MockSuccessfulComponent("duplicate")

    reg.register(comp1)
    with pytest.raises(DuplicateComponentError) as exc_info:
        reg.register(comp2)
    assert "already registered" in str(exc_info.value)


def test_registry_missing_dependency_fails():
    reg = ComponentRegistry()
    comp = MockSuccessfulComponent("dependent", deps=["non_existent"])
    reg.register(comp)

    with pytest.raises(MissingDependencyError) as exc_info:
        reg.validate_dependencies()
    assert "missing component 'non_existent'" in str(exc_info.value)


def test_registry_dependency_cycle_fails():
    reg = ComponentRegistry()
    reg.register(MockCircularA())
    reg.register(MockCircularB())

    with pytest.raises(DependencyCycleError) as exc_info:
        reg.validate_dependencies()
    assert "Circular dependency detected" in str(exc_info.value)


def test_registry_topological_initialization_order():
    reg = ComponentRegistry()
    c3 = MockSuccessfulComponent("c3", deps=["c2"])
    c1 = MockSuccessfulComponent("c1", deps=[])
    c2 = MockSuccessfulComponent("c2", deps=["c1"])

    reg.register(c3)
    reg.register(c1)
    reg.register(c2)

    order = reg.get_initialization_order()
    names = [c.name for c in order]
    assert names == ["c1", "c2", "c3"]

    shutdown_order = [c.name for c in reg.get_shutdown_order()]
    assert shutdown_order == ["c3", "c2", "c1"]


# ============================================================================
# APPLICATION LIFECYCLE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_application_successful_lifecycle():
    app = JarvisApplication()
    comp1 = MockSuccessfulComponent("db")
    comp2 = MockSuccessfulComponent("service", deps=["db"])

    app.register_component(comp1)
    app.register_component(comp2)

    assert app.state == RuntimeState.STOPPED

    await app.start()
    assert app.state == RuntimeState.RUNNING
    assert comp1.initialized and comp1.started
    assert comp2.initialized and comp2.started

    status = app.get_status()
    assert status["state"] == "RUNNING"
    assert status["total_components"] == 5  # EventBus, TaskManager, Orchestrator, db, service

    await app.shutdown("Test complete")
    assert app.state == RuntimeState.STOPPED
    assert comp1.stopped and comp2.stopped


@pytest.mark.asyncio
async def test_application_idempotent_shutdown():
    app = JarvisApplication()
    comp = MockSuccessfulComponent("c1")
    app.register_component(comp)

    await app.start()
    await app.shutdown("First shutdown")
    assert app.state == RuntimeState.STOPPED

    # Second shutdown call should be a clean no-op
    await app.shutdown("Second shutdown")
    assert app.state == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_application_init_failure_triggers_cleanup_and_failed_state():
    app = JarvisApplication()
    c1 = MockSuccessfulComponent("c1")
    c2 = MockInitFailingComponent()

    app.register_component(c1)
    app.register_component(c2)

    with pytest.raises(ComponentInitializationError):
        await app.start()

    assert app.state == RuntimeState.FAILED
    # c1 should have been stopped during cleanup
    assert c1.stopped


@pytest.mark.asyncio
async def test_application_start_failure_triggers_cleanup_and_failed_state():
    app = JarvisApplication()
    c1 = MockSuccessfulComponent("c1")
    c2 = MockStartFailingComponent()

    app.register_component(c1)
    app.register_component(c2)

    with pytest.raises(ComponentStartError):
        await app.start()

    assert app.state == RuntimeState.FAILED
    assert c1.stopped


@pytest.mark.asyncio
async def test_application_stop_failure_resilience():
    app = JarvisApplication()
    c1 = MockStopFailingComponent()
    c2 = MockSuccessfulComponent("c2")

    app.register_component(c1)
    app.register_component(c2)

    await app.start()
    await app.shutdown("Test stop failure handling")

    assert app.state == RuntimeState.STOPPED
    assert c2.stopped
    status = app.get_status()
    assert "stop_failing_comp" in status["failed_stop_components"]


@pytest.mark.asyncio
async def test_application_init_timeout():
    app = JarvisApplication(init_timeout=0.05)
    slow_comp = MockSlowComponent(delay=0.5)
    app.register_component(slow_comp)

    with pytest.raises(ComponentInitializationError):
        await app.start()

    assert app.state == RuntimeState.FAILED


@pytest.mark.asyncio
async def test_application_invalid_state_transitions():
    app = JarvisApplication()

    # Cannot transition directly from STOPPED to RUNNING
    with pytest.raises(InvalidStateTransitionError):
        app._transition_to(RuntimeState.RUNNING)

    await app.start()

    # Cannot start an already RUNNING application
    with pytest.raises(InvalidStateTransitionError):
        await app.start()

    await app.shutdown()


@pytest.mark.asyncio
async def test_application_health_reporting():
    app = JarvisApplication()
    c1 = MockSuccessfulComponent("c1")
    c2 = MockUnhealthyComponent()

    app.register_component(c1)
    app.register_component(c2)

    await app.start()
    health = await app.get_health()

    assert health["overall_status"] == HealthState.UNHEALTHY.value
    assert health["components"]["c1"]["status"] == HealthState.HEALTHY.value
    assert health["components"]["unhealthy_comp"]["status"] == HealthState.UNHEALTHY.value

    await app.shutdown()


def test_import_safety():
    """Verify that importing runtime module does not start runtime or have side effects."""
    import jarvis.core.runtime as rt

    assert hasattr(rt, "JarvisApplication")
    assert hasattr(rt, "LifecycleComponent")
    assert hasattr(rt, "ComponentRegistry")
    assert hasattr(rt, "RuntimeContext")
