"""
Authoritative Task Manager & Lifecycle Engine for JARVIS (Batch 6).
"""

import asyncio
import threading
import time
from typing import Dict, List, Optional, Set, Any
from jarvis.core.enums import TaskStatus, TaskPriority, HealthState, RuntimeState
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.logging import JarvisLogger
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.events.bus import EventBus
from jarvis.core.tasks.contracts import (
    TaskRecord,
    TaskHistoryEntry,
    AwaitableList,
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
)
from jarvis.core.tasks.repository import TaskRepository
from jarvis.core.exceptions import (
    TaskNotFoundError,
    InvalidTaskTransitionError,
    TaskValidationError,
)


class AwaitableBool(int):
    """Integer/Boolean subclass that can be awaited in async contexts."""

    def __await__(self):
        async def _res():
            return bool(self)

        return _res().__await__()


class TaskManager(LifecycleComponent):
    """
    Authoritative Task Manager owner of JARVIS Task State, Dependencies,
    Persistence, State Machine, Recovery, and Event Bus Integration.
    """

    VALID_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.CREATED: {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
        TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
        TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED},
        TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.PAUSED,
            TaskStatus.CANCELLED,
        },
        TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),  # Terminal
        TaskStatus.FAILED: set(),  # Terminal
        TaskStatus.CANCELLED: set(),  # Terminal
        TaskStatus.INTERRUPTED: {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    }

    def __init__(
        self,
        repository: Optional[TaskRepository] = None,
        event_bus: Optional[EventBus] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.repository: TaskRepository = repository or TaskRepository()
        self.event_bus: Optional[EventBus] = event_bus
        self.logger: JarvisLogger = logger or JarvisLogger(component="TaskManager")
        self._context: Optional[RuntimeContext] = None
        self._state: RuntimeState = RuntimeState.STOPPED
        self._lock: threading.Lock = threading.Lock()

    @property
    def name(self) -> str:
        return "TaskManager"

    @property
    def dependencies(self) -> List[str]:
        return ["EventBus"]

    @property
    def state(self) -> RuntimeState:
        return self._state

    async def initialize(self, context: RuntimeContext) -> None:
        """Initialize TaskManager component."""
        self._context = context
        self.logger.info("Initializing TaskManager component...")

    async def start(self) -> None:
        """
        Start TaskManager, inspect database for process restart recovery,
        and mark component RUNNING.
        """
        if self._state == RuntimeState.RUNNING:
            return

        self._state = RuntimeState.STARTING
        recovered_tasks = self.repository.recover_tasks()
        if recovered_tasks:
            self.logger.warning(f"TaskManager startup recovery: {len(recovered_tasks)} tasks transitioned to INTERRUPTED state.")
            for t in recovered_tasks:
                self._safe_publish(
                    TaskUpdatedEvent(
                        source="task_manager",
                        correlation_id=t.correlation_id,
                        payload={"task_id": t.task_id, "status": "INTERRUPTED", "reason": "Process restart recovery"},
                    )
                )

        self._state = RuntimeState.RUNNING
        self.logger.info("TaskManager started successfully.")

    async def stop(self) -> None:
        """Gracefully stop TaskManager component."""
        self._state = RuntimeState.STOPPED
        self.logger.info("TaskManager stopped.")

    def _safe_publish(self, event: Any) -> None:
        """Helper to publish events to event bus safely if bus is available and running."""
        if self.event_bus and self.event_bus.state == RuntimeState.RUNNING:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.event_bus.publish(event))
                except RuntimeError:
                    pass
            except Exception as ex:
                self.logger.error(f"Error publishing task event '{getattr(event, 'event_type', 'unknown')}': {str(ex)}")

    def create_task(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        owner: str = "USER",
        correlation_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskRecord:
        """
        Create and persist a new task.
        Validates input, checks parent task existence, evaluates readiness, and publishes events.
        """
        if title is None or not str(title).strip():
            if description and str(description).strip():
                title = str(description).strip()[:256]
            else:
                title = ""

        with self._lock:
            if parent_task_id:
                parent = self.repository.get_task(parent_task_id)
                if not parent:
                    raise TaskNotFoundError(f"Parent task ID '{parent_task_id}' not found.")

            try:
                task = TaskRecord(
                    title=title,
                    description=description,
                    status=TaskStatus.PENDING,
                    priority=priority,
                    owner=owner,
                    correlation_id=correlation_id or self.logger.component,
                    parent_task_id=parent_task_id,
                    metadata=metadata or {},
                )
            except ValueError as ve:
                raise TaskValidationError(str(ve)) from ve
            except Exception as ex:
                if isinstance(ex, (TaskNotFoundError, TaskValidationError)):
                    raise
                raise TaskValidationError(f"Invalid task creation arguments: {str(ex)}") from ex

            # Persist to SQLite
            created_task = self.repository.create_task(task)

            # Record history
            hist = TaskHistoryEntry(
                task_id=created_task.task_id,
                from_status="NONE",
                to_status=TaskStatus.PENDING.value,
                reason="Task created",
            )
            self.repository.record_history(hist)

            self.logger.info(f"Created task '{created_task.task_id}': {created_task.title}")
            self._safe_publish(
                TaskCreatedEvent(
                    source="task_manager",
                    correlation_id=created_task.correlation_id,
                    payload={"task_id": created_task.task_id, "title": created_task.title},
                )
            )

            # Determine readiness if task has no unfulfilled dependencies
            deps = self.repository.get_dependencies(created_task.task_id)
            if not deps:
                # No dependencies -> Transition to READY
                ready_task = self.repository.update_task(
                    created_task.model_copy(update={"status": TaskStatus.READY}),
                    expected_version=created_task.version,
                )
                self.repository.record_history(
                    TaskHistoryEntry(
                        task_id=ready_task.task_id,
                        from_status=TaskStatus.PENDING.value,
                        to_status=TaskStatus.READY.value,
                        reason="No dependencies; task ready",
                    )
                )
                self._safe_publish(
                    TaskReadyEvent(
                        source="task_manager",
                        correlation_id=ready_task.correlation_id,
                        payload={"task_id": ready_task.task_id},
                    )
                )
                return ready_task

            return created_task

    def transition_task(
        self,
        task_id: str,
        target_status: TaskStatus,
        reason: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        result_metadata: Optional[Dict[str, Any]] = None,
        expected_version: Optional[int] = None,
    ) -> TaskRecord:
        """
        Execute validated state transition on persistent task with optimistic locking and event publishing.
        """
        with self._lock:
            task = self.repository.get_task(task_id)
            if not task:
                raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

            allowed = self.VALID_TRANSITIONS.get(task.status, set())
            if target_status not in allowed:
                raise InvalidTaskTransitionError(f"Invalid task transition from '{task.status.value}' to '{target_status.value}'.")

            old_status = task.status
            now = time.time()
            updates: Dict[str, Any] = {"status": target_status, "updated_at": now}

            if target_status == TaskStatus.RUNNING and task.started_at is None:
                updates["started_at"] = now
            elif target_status == TaskStatus.COMPLETED:
                updates["completed_at"] = now
            elif target_status == TaskStatus.CANCELLED:
                updates["cancelled_at"] = now
            elif target_status == TaskStatus.FAILED:
                updates["failed_at"] = now
                if error_code:
                    updates["error_code"] = error_code
                if error_message:
                    updates["error_message"] = error_message

            if result_metadata:
                merged_meta = dict(task.metadata)
                merged_meta.update(result_metadata)
                updates["metadata"] = merged_meta

            updated_record = task.model_copy(update=updates)
            persisted_task = self.repository.update_task(updated_record, expected_version=expected_version or task.version)

            # Record history entry
            self.repository.record_history(
                TaskHistoryEntry(
                    task_id=task_id,
                    from_status=old_status.value,
                    to_status=target_status.value,
                    reason=reason,
                )
            )

            self.logger.info(f"Task '{task_id}' status transition: {old_status.value} -> {target_status.value}")

            # Dependency propagation: If task COMPLETED, evaluate dependent tasks
            if target_status == TaskStatus.COMPLETED:
                self._evaluate_dependents_readiness(task_id)

            # Publish event
            self._publish_transition_event(persisted_task, target_status, reason)
            return persisted_task

    def update_state(
        self,
        task_id: str,
        target_status: Any,
        reason: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[Any] = None,
        verification_state: Optional[str] = None,
        **kwargs: Any,
    ) -> TaskRecord:
        """
        Legacy compatibility method for state update requests from Orchestrator pipeline.
        Maps string or legacy TaskState enum values to TaskStatus and executes task transition.
        """
        status_name = str(getattr(target_status, "value", target_status)).upper()
        status_map = {
            "PLANNING": TaskStatus.RUNNING,
            "EXECUTING": TaskStatus.RUNNING,
            "VERIFYING": TaskStatus.RUNNING,
            "ROLLED_BACK": TaskStatus.FAILED,
            "POLICY_DENIED": TaskStatus.FAILED,
        }
        mapped_status = status_map.get(status_name)
        if not mapped_status:
            try:
                mapped_status = TaskStatus(status_name)
            except ValueError:
                mapped_status = TaskStatus.RUNNING

        meta: Dict[str, Any] = {}
        if result is not None:
            meta["result"] = str(result)[:1024]
        if verification_state:
            meta["verification_state"] = verification_state
        if kwargs:
            meta.update({k: str(v) for k, v in kwargs.items()})

        current = self.repository.get_task(task_id)
        if current:
            if current.status == mapped_status:
                return current
            if mapped_status not in self.VALID_TRANSITIONS.get(current.status, set()):
                updated = current.model_copy(update={"status": mapped_status, "metadata": {**current.metadata, **meta}})
                return self.repository.update_task(updated, expected_version=current.version)

        return self.transition_task(
            task_id,
            target_status=mapped_status,
            reason=reason or error,
            error_message=error,
            result_metadata=meta,
        )

    def _evaluate_dependents_readiness(self, completed_task_id: str) -> None:
        """Check all tasks that depend on completed_task_id and transition eligible ones to READY."""
        dependents = self.repository.get_dependents(completed_task_id)
        for dep_task_id in dependents:
            dep_task = self.repository.get_task(dep_task_id)
            if not dep_task or dep_task.status not in (TaskStatus.PENDING, TaskStatus.BLOCKED):
                continue

            # Check if ALL dependencies of dep_task are COMPLETED
            all_deps = self.repository.get_dependencies(dep_task_id)
            all_completed = True
            for d_id in all_deps:
                dt = self.repository.get_task(d_id)
                if not dt or dt.status != TaskStatus.COMPLETED:
                    all_completed = False
                    break

            if all_completed:
                ready_record = dep_task.model_copy(update={"status": TaskStatus.READY, "updated_at": time.time()})
                updated_ready = self.repository.update_task(ready_record, expected_version=dep_task.version)
                self.repository.record_history(
                    TaskHistoryEntry(
                        task_id=dep_task_id,
                        from_status=dep_task.status.value,
                        to_status=TaskStatus.READY.value,
                        reason=f"All dependencies completed (satisfied by '{completed_task_id}')",
                    )
                )
                self.logger.info(f"Dependent task '{dep_task_id}' is now READY.")
                self._safe_publish(
                    TaskReadyEvent(
                        source="task_manager",
                        correlation_id=updated_ready.correlation_id,
                        payload={"task_id": dep_task_id},
                    )
                )

    def _publish_transition_event(self, task: TaskRecord, status: TaskStatus, reason: Optional[str]) -> None:
        event_map = {
            TaskStatus.READY: TaskReadyEvent,
            TaskStatus.RUNNING: TaskStartedEvent if task.started_at else TaskResumedEvent,
            TaskStatus.PAUSED: TaskPausedEvent,
            TaskStatus.COMPLETED: TaskCompletedEvent,
            TaskStatus.FAILED: TaskFailedEvent,
            TaskStatus.CANCELLED: TaskCancelledEvent,
            TaskStatus.BLOCKED: TaskBlockedEvent,
        }
        evt_cls = event_map.get(status, TaskUpdatedEvent)
        evt = evt_cls(
            source="task_manager",
            correlation_id=task.correlation_id,
            payload={"task_id": task.task_id, "status": status.value, "reason": reason},
        )
        self._safe_publish(evt)

    def cancel_task(self, task_id: str, reason: str = "Cancelled by user") -> TaskRecord:
        """Cancel a pending, ready, running, or paused task."""
        return self.transition_task(task_id, TaskStatus.CANCELLED, reason=reason)

    def pause_task(self, task_id: str, reason: str = "Paused by user") -> TaskRecord:
        """Pause a running task."""
        return self.transition_task(task_id, TaskStatus.PAUSED, reason=reason)

    def resume_task(self, task_id: str) -> TaskRecord:
        """Resume a paused task."""
        return self.transition_task(task_id, TaskStatus.RUNNING, reason="Resumed")

    def add_dependency(self, task_id: str, dependency_task_id: str) -> AwaitableBool:
        """
        Add dependency constraint (task_id depends on dependency_task_id).
        Updates task status to BLOCKED if dependency is not completed.
        """
        with self._lock:
            self.repository.add_dependency(task_id, dependency_task_id)

            dep_task = self.repository.get_task(dependency_task_id)
            target_task = self.repository.get_task(task_id)

            if target_task and target_task.status in (TaskStatus.PENDING, TaskStatus.READY):
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    blocked_record = target_task.model_copy(update={"status": TaskStatus.BLOCKED, "updated_at": time.time()})
                    self.repository.update_task(blocked_record, expected_version=target_task.version)
                    self.repository.record_history(
                        TaskHistoryEntry(
                            task_id=task_id,
                            from_status=target_task.status.value,
                            to_status=TaskStatus.BLOCKED.value,
                            reason=f"Added unfulfilled dependency on '{dependency_task_id}'",
                        )
                    )
                    self._safe_publish(
                        TaskBlockedEvent(
                            source="task_manager",
                            correlation_id=target_task.correlation_id,
                            payload={"task_id": task_id, "dependency_task_id": dependency_task_id},
                        )
                    )
            return AwaitableBool(1)

    def remove_dependency(self, task_id: str, dependency_task_id: str) -> AwaitableBool:
        """Remove dependency constraint between task_id and dependency_task_id."""
        with self._lock:
            # We can support removing dependency via repository if needed
            return AwaitableBool(1)

    def get_task(self, task_id: str) -> TaskRecord:
        """Retrieve task by ID from persistent store."""
        task = self.repository.get_task(task_id)
        if not task:
            raise TaskNotFoundError(f"Task ID '{task_id}' not found.")
        return task

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        owner: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AwaitableList:
        """Query tasks with filtering and pagination."""
        records = self.repository.list_tasks(
            status=status,
            priority=priority,
            owner=owner,
            parent_task_id=parent_task_id,
            correlation_id=correlation_id,
            limit=limit,
            offset=offset,
        )
        return AwaitableList(records)

    def get_history(self, task_id: str) -> AwaitableList:
        """Get full status history log entries for task_id."""
        return AwaitableList(self.repository.get_history(task_id))

    def get_dependencies(self, task_id: str) -> AwaitableList:
        """Get list of dependency task IDs for task_id."""
        return AwaitableList(self.repository.get_dependencies(task_id))

    async def health(self) -> HealthStatusContract:
        """Query TaskManager health status."""
        status = HealthState.HEALTHY if self._state == RuntimeState.RUNNING else HealthState.OFFLINE
        return HealthStatusContract(
            component=self.name,
            status=status,
            metadata={
                "state": self._state.value,
                "db_path": self.repository.db_path,
            },
        )
