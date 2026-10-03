"""
Authoritative JARVIS Application Runtime & Lifecycle Kernel.
"""

import asyncio
import signal
import sys
import time
from typing import Dict, List, Optional, Set, Any
from config.settings import Settings, get_settings
from jarvis.core.enums import RuntimeState, HealthState
from jarvis.core.logging import JarvisLogger
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.runtime.registry import ComponentRegistry
from jarvis.core.exceptions import (
    InvalidStateTransitionError,
    ComponentInitializationError,
    ComponentStartError,
)


from jarvis.core.events.bus import EventBus
from jarvis.core.events.contracts import (
    RuntimeStartingEvent,
    RuntimeStartedEvent,
    RuntimeStoppingEvent,
    RuntimeFailedEvent,
    ComponentRegisteredEvent,
    ComponentInitializingEvent,
    ComponentInitializedEvent,
    ComponentStartedEvent,
    ComponentStoppedEvent,
    ComponentFailedEvent,
)
from jarvis.core.tasks.manager import TaskManager
from jarvis.core.orchestration.orchestrator import Orchestrator


class JarvisApplication:
    """
    Authoritative owner of JARVIS runtime lifecycle, component orchestration,
    health inspection, and process signal handling.
    """

    VALID_TRANSITIONS: Dict[RuntimeState, Set[RuntimeState]] = {
        RuntimeState.STOPPED: {RuntimeState.STARTING},
        RuntimeState.STARTING: {RuntimeState.INITIALIZING, RuntimeState.FAILED},
        RuntimeState.INITIALIZING: {
            RuntimeState.RUNNING,
            RuntimeState.FAILED,
            RuntimeState.STOPPING,
        },
        RuntimeState.RUNNING: {RuntimeState.STOPPING, RuntimeState.FAILED},
        RuntimeState.STOPPING: {RuntimeState.STOPPED, RuntimeState.FAILED},
        RuntimeState.FAILED: {RuntimeState.STOPPING, RuntimeState.STOPPED},
    }

    def __init__(
        self,
        settings: Optional[Settings] = None,
        logger: Optional[JarvisLogger] = None,
        event_bus: Optional[EventBus] = None,
        task_manager: Optional[TaskManager] = None,
        orchestrator: Optional[Orchestrator] = None,
        init_timeout: float = 10.0,
        start_timeout: float = 10.0,
        shutdown_timeout: float = 10.0,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        self.logger: JarvisLogger = logger or JarvisLogger(component="Runtime")
        self.event_bus: EventBus = event_bus or EventBus(logger=JarvisLogger(component="EventBus"))
        self.task_manager: TaskManager = task_manager or TaskManager(event_bus=self.event_bus, logger=JarvisLogger(component="TaskManager"))
        self.orchestrator: Orchestrator = orchestrator or Orchestrator(
            event_bus=self.event_bus,
            task_manager=self.task_manager,
            logger=JarvisLogger(component="Orchestrator"),
        )
        self.registry: ComponentRegistry = ComponentRegistry()
        self.context: RuntimeContext = RuntimeContext(settings=self.settings, logger=self.logger)

        self._state: RuntimeState = RuntimeState.STOPPED
        self.init_timeout: float = init_timeout
        self.start_timeout: float = start_timeout
        self.shutdown_timeout: float = shutdown_timeout

        self.shutdown_reason: Optional[str] = None
        self._initialized_components: List[LifecycleComponent] = []
        self._started_components: List[LifecycleComponent] = []
        self._failed_stop_components: List[str] = []
        self._shutdown_lock: asyncio.Lock = asyncio.Lock()
        self._shutdown_task: Optional[asyncio.Task] = None
        self._background_tasks: Set[asyncio.Task] = set()

        # Automatically register EventBus, TaskManager, and Orchestrator into registry
        self.register_component(self.event_bus)
        self.register_component(self.task_manager)
        self.register_component(self.orchestrator)

    @property
    def state(self) -> RuntimeState:
        """Current runtime state."""
        return self._state

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        """Track background task and retrieve exception on completion."""
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    self.logger.error(
                        f"Background task '{t.get_name()}' failed with exception: {exc}",
                        exc_info=exc,
                    )

        task.add_done_callback(_on_done)
        return task

    def register_component(self, component: LifecycleComponent) -> None:
        """Register a lifecycle component with the application runtime."""
        self.registry.register(component)
        self.logger.info(
            f"Registered runtime component: '{component.name}'",
            extra={"component_name": component.name},
        )
        self._safe_publish(
            ComponentRegisteredEvent(
                source="runtime",
                correlation_id=self.context.app_id,
                payload={"component_name": component.name},
            )
        )

    def _safe_publish(self, event: Any) -> None:
        """Helper to publish events safely without throwing when bus is not running."""
        try:
            if self._state == RuntimeState.RUNNING and self.event_bus.state == RuntimeState.RUNNING:
                task = asyncio.create_task(self.event_bus.publish(event))
                self._track_task(task)
        except Exception as ex:
            self.logger.info(f"Event publish skipped: {ex}")

    def _transition_to(self, new_state: RuntimeState) -> None:
        """Validate and execute state transition."""
        allowed = self.VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(f"Invalid runtime state transition from '{self._state.value}' to '{new_state.value}'.")
        old_state = self._state
        self._state = new_state
        self.logger.info(
            f"Runtime state transition: {old_state.value} -> {new_state.value}",
            extra={"old_state": old_state.value, "new_state": new_state.value},
        )

    async def start(self) -> None:
        """
        Execute application startup: validate environment security, validate dependencies,
        initialize components, and start components in deterministic order.
        """
        if self._state != RuntimeState.STOPPED:
            raise InvalidStateTransitionError(f"Cannot start runtime when in state '{self._state.value}'.")

        self._transition_to(RuntimeState.STARTING)
        self.context.startup_timestamp = time.time()
        self.logger.info("JARVIS Application Runtime starting...")

        # 0. Validate Environment Security
        try:
            from config.env_security import validate_environment

            validate_environment()
        except Exception as e:
            self._transition_to(RuntimeState.FAILED)
            self.logger.error(f"Startup environment security validation failed: {str(e)}")
            self._safe_publish(RuntimeFailedEvent(source="runtime", correlation_id=self.context.app_id, payload={"error": str(e)}))
            raise

        # 1. Validate dependencies
        try:
            self.registry.validate_dependencies()
        except Exception as e:
            self._transition_to(RuntimeState.FAILED)
            self.logger.error(f"Startup dependency validation failed: {str(e)}")
            self._safe_publish(RuntimeFailedEvent(source="runtime", correlation_id=self.context.app_id, payload={"error": str(e)}))
            raise

        # 1.5 Execute Persistent State Recovery
        try:
            from jarvis.core.recovery.coordinator import RecoveryCoordinator

            coordinator = RecoveryCoordinator(
                task_manager=self.task_manager,
                event_bus=self.event_bus,
                db_path=getattr(self.task_manager.repository, "db_path", "data/jarvis.db"),
            )
            coordinator.execute_recovery()
        except Exception as e:
            self.logger.error(f"Startup persistent state recovery failed: {str(e)}")
            self._transition_to(RuntimeState.FAILED)
            self._safe_publish(RuntimeFailedEvent(source="runtime", correlation_id=self.context.app_id, payload={"error": str(e)}))
            raise

        # 2. Initialize components
        self._transition_to(RuntimeState.INITIALIZING)
        init_order = self.registry.get_initialization_order()

        for comp in init_order:
            self.logger.info(f"Initializing component: '{comp.name}'")
            self._safe_publish(
                ComponentInitializingEvent(
                    source="runtime",
                    correlation_id=self.context.app_id,
                    payload={"component_name": comp.name},
                )
            )
            try:
                await asyncio.wait_for(comp.initialize(self.context), timeout=self.init_timeout)
                self._initialized_components.append(comp)
                self.logger.info(f"Initialized component cleanly: '{comp.name}'")
                self._safe_publish(
                    ComponentInitializedEvent(
                        source="runtime",
                        correlation_id=self.context.app_id,
                        payload={"component_name": comp.name},
                    )
                )
            except Exception as e:
                self.logger.error(f"Component '{comp.name}' initialization failed: {str(e)}")
                self._transition_to(RuntimeState.FAILED)
                self._safe_publish(
                    ComponentFailedEvent(
                        source="runtime",
                        correlation_id=self.context.app_id,
                        payload={"component_name": comp.name, "stage": "initialize", "error": str(e)},
                    )
                )
                await self._cleanup_on_startup_failure()
                raise ComponentInitializationError(f"Initialization failed for component '{comp.name}': {str(e)}") from e

        # 3. Start components
        self._transition_to(RuntimeState.RUNNING)
        self._safe_publish(RuntimeStartingEvent(source="runtime", correlation_id=self.context.app_id))

        for comp in init_order:
            self.logger.info(f"Starting component: '{comp.name}'")
            try:
                await asyncio.wait_for(comp.start(), timeout=self.start_timeout)
                self._started_components.append(comp)
                self.logger.info(f"Started component cleanly: '{comp.name}'")
                self._safe_publish(
                    ComponentStartedEvent(
                        source="runtime",
                        correlation_id=self.context.app_id,
                        payload={"component_name": comp.name},
                    )
                )
            except Exception as e:
                self.logger.error(f"Component '{comp.name}' start failed: {str(e)}")
                self._transition_to(RuntimeState.FAILED)
                self._safe_publish(
                    ComponentFailedEvent(
                        source="runtime",
                        correlation_id=self.context.app_id,
                        payload={"component_name": comp.name, "stage": "start", "error": str(e)},
                    )
                )
                await self._cleanup_on_startup_failure()
                raise ComponentStartError(f"Start failed for component '{comp.name}': {str(e)}") from e

        self.logger.info("JARVIS Application Runtime is RUNNING.")
        self._safe_publish(RuntimeStartedEvent(source="runtime", correlation_id=self.context.app_id))

    async def _cleanup_on_startup_failure(self) -> None:
        """Stop already-started or initialized components during startup failure."""
        self.logger.warning("Executing cleanup for components due to startup failure...")
        # Teardown started components in reverse order
        for comp in reversed(self._started_components):
            try:
                await asyncio.wait_for(comp.stop(), timeout=self.shutdown_timeout)
            except Exception as ex:
                self.logger.error(f"Error stopping component '{comp.name}' during startup failure cleanup: {str(ex)}")
        # Teardown initialized but not started components
        unstarted = [c for c in self._initialized_components if c not in self._started_components]
        for comp in reversed(unstarted):
            try:
                await asyncio.wait_for(comp.stop(), timeout=self.shutdown_timeout)
            except Exception as ex:
                self.logger.error(f"Error stopping initialized component '{comp.name}' during startup failure cleanup: {str(ex)}")

    async def shutdown(self, reason: str = "Graceful shutdown requested") -> None:
        """
        Gracefully stop all components in reverse dependency order.
        Idempotent: safe to call repeatedly.
        """
        async with self._shutdown_lock:
            if self._state in (RuntimeState.STOPPING, RuntimeState.STOPPED):
                self.logger.info(f"Shutdown requested but runtime is already in '{self._state.value}' state.")
                return

            self.shutdown_reason = reason
            self.logger.info(f"Initiating shutdown: {reason}")
            self.context.cancellation_event.set()

            # Transition to STOPPING
            self._transition_to(RuntimeState.STOPPING)
            self._safe_publish(RuntimeStoppingEvent(source="runtime", correlation_id=self.context.app_id, payload={"reason": reason}))

            # Components to stop: started ones first, then initialized ones, ensuring EventBus stops LAST
            all_comps: List[LifecycleComponent] = []
            for comp in reversed(self._started_components):
                if comp not in all_comps:
                    all_comps.append(comp)
            for comp in reversed(self._initialized_components):
                if comp not in all_comps:
                    all_comps.append(comp)

            # Separate non-EventBus components and EventBus
            to_stop = [c for c in all_comps if c != self.event_bus]
            if self.event_bus in all_comps:
                to_stop.append(self.event_bus)

            for comp in to_stop:
                self.logger.info(f"Stopping component: '{comp.name}'")
                try:
                    await asyncio.wait_for(comp.stop(), timeout=self.shutdown_timeout)
                    self.logger.info(f"Stopped component cleanly: '{comp.name}'")
                    self._safe_publish(ComponentStoppedEvent(source="runtime", correlation_id=self.context.app_id, payload={"component_name": comp.name}))
                except Exception as e:
                    self.logger.error(f"Error stopping component '{comp.name}': {str(e)}")
                    self._failed_stop_components.append(comp.name)

            # Await or cancel remaining application background tasks
            if self._background_tasks:
                pending = [t for t in list(self._background_tasks) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                self._background_tasks.clear()

            self._transition_to(RuntimeState.STOPPED)
            self.logger.info("JARVIS Application Runtime has STOPPED.")

    async def get_health(self) -> Dict[str, Any]:
        """Aggregate health statuses across all registered components."""
        results: Dict[str, Any] = {
            "runtime_state": self._state.value,
            "overall_status": HealthState.HEALTHY.value,
            "components": {},
        }

        overall_unhealthy = False
        overall_degraded = False

        for comp in self.registry.all_components():
            try:
                h = await comp.health()
                results["components"][comp.name] = h.model_dump()
                if h.status == HealthState.UNHEALTHY:
                    overall_unhealthy = True
                elif h.status == HealthState.DEGRADED:
                    overall_degraded = True
            except Exception as e:
                results["components"][comp.name] = {
                    "component": comp.name,
                    "status": HealthState.UNHEALTHY.value,
                    "error": str(e),
                }
                overall_unhealthy = True

        if overall_unhealthy:
            results["overall_status"] = HealthState.UNHEALTHY.value
        elif overall_degraded:
            results["overall_status"] = HealthState.DEGRADED.value

        return results

    def get_status(self) -> Dict[str, Any]:
        """Return serializable runtime status metrics."""
        return {
            "state": self._state.value,
            "uptime_seconds": round(self.context.get_uptime(), 2),
            "app_id": self.context.app_id,
            "session_id": self.context.session_id,
            "total_components": self.registry.count(),
            "initialized_components": [c.name for c in self._initialized_components],
            "started_components": [c.name for c in self._started_components],
            "failed_stop_components": list(self._failed_stop_components),
            "shutdown_reason": self.shutdown_reason,
        }

    def setup_signal_handlers(self) -> None:
        """Register process signal handlers for SIGINT and SIGTERM where supported."""
        loop = asyncio.get_event_loop()

        def signal_handler(sig_name: str) -> None:
            self.logger.info(f"Received process signal: {sig_name}")
            asyncio.create_task(self.shutdown(reason=f"Received signal {sig_name}"))

        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, lambda s=sig: signal_handler(s.name))
                except NotImplementedError:
                    pass

    async def run_until_shutdown(self, run_duration: Optional[float] = None) -> None:
        """
        Helper method to run application until shutdown event or specified duration.
        """
        await self.start()
        self.setup_signal_handlers()

        try:
            if run_duration is not None:
                await asyncio.wait_for(self.context.cancellation_event.wait(), timeout=run_duration)
            else:
                await self.context.cancellation_event.wait()
        except asyncio.TimeoutError:
            self.logger.info("Run duration expired, initiating shutdown.")
        finally:
            await self.shutdown(reason="Application execution completed")
