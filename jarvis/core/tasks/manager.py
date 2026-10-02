"""
Authoritative Task Manager & Persistent Lifecycle Coordinator for JARVIS (Batch 6 & Batch 17).
Coordinates TaskRepository, TaskStateMachine, TaskRecoveryService, PolicyEngine, and EventBus.
"""

import uuid
from typing import List, Optional, Dict, Any
from jarvis.core.enums import TaskStatus, TaskPriority
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.logging import JarvisLogger
from jarvis.core.tasks.contracts import (
    TaskRecord,
    TaskHistoryEntry,
    TaskType,
    TaskRecoveryReport,
    AwaitableList,
    AwaitableNone,
)
from jarvis.core.tasks.repository import TaskRepository
from jarvis.core.tasks.recovery import TaskRecoveryService
from jarvis.core.tasks.outbox import TaskEventPublisher
from jarvis.core.tasks.exceptions import (
    TaskNotFoundError,
    TaskDuplicateIdempotencyError,
    TaskAuthorizationError,
)
from jarvis.security.policy import PolicyEngine, ApprovalEngine, PolicyRepository, AuthorizationRequest, Principal


class TaskManager(LifecycleComponent):
    """
    Authoritative Central Task Manager.
    Coordinates task lifecycle, persistence, state transitions, dependencies, restart recovery,
    authorization, and event bus delivery.
    """

    def __init__(
        self,
        repository: Optional[TaskRepository] = None,
        event_bus: Optional[Any] = None,
        policy_engine: Optional[PolicyEngine] = None,
        logger: Optional[JarvisLogger] = None,
        db_path: str = "data/jarvis.db",
    ) -> None:
        self.repository = repository or TaskRepository(db_path=db_path)
        self.event_bus = event_bus
        self.policy_engine = policy_engine or PolicyEngine(approval_engine=ApprovalEngine(repository=PolicyRepository(db_path=db_path)))
        self.logger = logger or JarvisLogger(component="TaskManager")

        self.event_publisher = TaskEventPublisher(event_bus=self.event_bus)
        self.recovery_service = TaskRecoveryService(
            repository=self.repository,
            policy_engine=self.policy_engine,
        )

        self._state = "STOPPED"
        self._context: Optional[RuntimeContext] = None

    @property
    def name(self) -> str:
        return "TaskManager"

    @property
    def state(self) -> str:
        return self._state

    async def initialize(self, context: RuntimeContext) -> None:
        self._context = context
        self._state = "INITIALIZING"
        self.logger.info("Initializing TaskManager...")

    async def start(self) -> None:
        """
        Start TaskManager lifecycle:
        Runs startup restart recovery to handle interrupted tasks.
        """
        if self._state == "RUNNING":
            return
        self._state = "RUNNING"
        self.logger.info("Starting TaskManager and running startup task recovery...")
        recovery_report = self.recovery_service.recover_tasks()
        self.logger.info(f"Task recovery completed: inspected {recovery_report.total_inspected}, recovered {recovery_report.recovered_count}.")

    async def stop(self) -> None:
        self._state = "STOPPED"
        self.logger.info("TaskManager stopped.")

    def _authorize(self, principal: Optional[Principal], action: str, resource: str) -> None:
        """Helper to authorize task operation against policy engine."""
        if not principal:
            return  # Internal call without principal bypasses policy, but external principal checks apply

        auth_req = AuthorizationRequest(
            principal=principal,
            action=action,
            resource=resource,
        )
        dec = self.policy_engine.evaluate(auth_req)
        if not dec.allowed:
            raise TaskAuthorizationError(f"Task operation '{action}' on '{resource}' denied by policy: {dec.reason}")

    def create_task(
        self,
        title: str = "Untitled Task",
        description: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        owner: str = "USER",
        task_type: TaskType = TaskType.GENERAL,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        principal: Optional[Principal] = None,
        **kwargs: Any,
    ) -> TaskRecord:
        """
        Create and persist a new task record.
        Enforces idempotency, input validation, authorization, and post-commit event publishing.
        """
        if title == "Untitled Task" and description:
            title = description[:100]

        self._authorize(principal, "filesystem.create", f"task:{title}")

        # Idempotency check
        if idempotency_key:
            existing = self.repository.get_task_by_idempotency_key(idempotency_key)
            if existing:
                if existing.title != title or existing.owner != owner:
                    raise TaskDuplicateIdempotencyError(f"Idempotency key '{idempotency_key}' reused with conflicting task payload.")
                return existing

        if parent_task_id:
            parent = self.repository.get_task(parent_task_id)
            if not parent:
                raise TaskNotFoundError(f"Parent task ID '{parent_task_id}' not found.")

        task_id = kwargs.get("task_id") or f"task-{uuid.uuid4().hex[:12]}"
        correlation_id = kwargs.get("correlation_id") or f"corr-{uuid.uuid4().hex[:8]}"

        meta = dict(metadata or {})
        rec = TaskRecord(
            task_id=task_id,
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
            owner=owner,
            task_type=task_type,
            idempotency_key=idempotency_key,
            parent_task_id=parent_task_id,
            correlation_id=correlation_id,
            metadata=meta,
            max_attempts=kwargs.get("max_attempts", 3),
        )

        saved = self.repository.create_task(rec)
        self.event_publisher.publish_task_created(saved)

        # Auto-transition to READY if task has no dependencies
        deps = self.repository.get_dependencies(saved.task_id)
        if not deps:
            saved = self.transition_task(
                task_id=saved.task_id,
                to_status=TaskStatus.READY,
                reason="Task created with no pending dependencies",
                actor_id="task_manager",
            )

        return saved

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self.repository.get_task(task_id)

    def transition_task(
        self,
        task_id: str,
        to_status: TaskStatus,
        reason: str = "State transition requested",
        actor_id: str = "USER",
        expected_version: Optional[int] = None,
        principal: Optional[Principal] = None,
    ) -> TaskRecord:
        """
        Atomically transition task status with state machine validation, version checks,
        and post-commit event publishing.
        """
        self._authorize(principal, "filesystem.modify", f"task:{task_id}")
        t = self.repository.get_task(task_id)
        if not t:
            raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

        old_status = t.status
        updated = self.repository.transition_task(
            task_id=task_id,
            to_status=to_status,
            reason=reason,
            actor_id=actor_id,
            expected_version=expected_version,
        )

        # Check dependent tasks readiness if transition is COMPLETED
        if to_status == TaskStatus.COMPLETED:
            self._propagate_dependency_readiness(task_id)
        elif to_status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED):
            self._propagate_dependency_blocked(task_id)

        self.event_publisher.publish_status_changed(updated, old_status=old_status)
        return updated

    def _propagate_dependency_readiness(self, completed_task_id: str) -> None:
        dependents = self.repository.get_dependents(completed_task_id)
        for dep_task_id in dependents:
            dep_task = self.repository.get_task(dep_task_id)
            if dep_task and dep_task.status in (TaskStatus.WAITING_DEPENDENCY, TaskStatus.QUEUED, TaskStatus.PENDING):
                dep_state = self.recovery_service.check_dependencies_satisfied(dep_task_id)
                if dep_state == "SATISFIED":
                    self.transition_task(
                        task_id=dep_task_id,
                        to_status=TaskStatus.READY,
                        reason=f"Prerequisite dependency '{completed_task_id}' completed successfully",
                        actor_id="task_manager",
                    )

    def _propagate_dependency_blocked(self, failed_task_id: str) -> None:
        dependents = self.repository.get_dependents(failed_task_id)
        for dep_task_id in dependents:
            dep_task = self.repository.get_task(dep_task_id)
            if dep_task and dep_task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED):
                self.transition_task(
                    task_id=dep_task_id,
                    to_status=TaskStatus.BLOCKED,
                    reason=f"Prerequisite dependency '{failed_task_id}' failed or was cancelled",
                    actor_id="task_manager",
                )

    def request_cancellation(self, task_id: str, reason: str = "User requested cancellation", principal: Optional[Principal] = None) -> TaskRecord:
        """
        Request task cancellation. Transitions running tasks to CANCELLING, non-running to CANCELLED.
        """
        self._authorize(principal, "filesystem.delete", f"task:{task_id}")
        t = self.repository.get_task(task_id)
        if not t:
            raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

        t.cancellation_requested = True
        self.repository.update_task(t)

        if t.status == TaskStatus.RUNNING:
            return self.transition_task(task_id, TaskStatus.CANCELLING, reason=reason, principal=principal)
        else:
            return self.transition_task(task_id, TaskStatus.CANCELLED, reason=reason, principal=principal)

    def cancel_task(self, task_id: str, reason: str = "User requested cancellation", principal: Optional[Principal] = None) -> TaskRecord:
        """Cancel task and transition to CANCELLED status."""
        self._authorize(principal, "filesystem.delete", f"task:{task_id}")
        t = self.repository.get_task(task_id)
        if not t:
            raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

        t.cancellation_requested = True
        self.repository.update_task(t)
        return self.transition_task(task_id, TaskStatus.CANCELLED, reason=reason, principal=principal)

    def update_state(
        self,
        task_id: str,
        new_state: str,
        error: Optional[str] = None,
        result: Optional[Any] = None,
        verification_state: Optional[str] = None,
    ) -> TaskRecord:
        """Backwards-compatible state updater for legacy pipeline integration."""
        try:
            status_enum = TaskStatus(new_state)
        except ValueError:
            status_enum = TaskStatus.RUNNING if new_state in ("PLANNING", "EXECUTING", "VERIFYING") else TaskStatus.FAILED
        return self.transition_task(task_id=task_id, to_status=status_enum, reason=error or f"State updated to {new_state}")

    def pause_task(self, task_id: str, reason: str = "User paused task", principal: Optional[Principal] = None) -> TaskRecord:
        return self.transition_task(task_id, TaskStatus.PAUSED, reason=reason, principal=principal)

    def resume_task(self, task_id: str, reason: str = "User resumed task", principal: Optional[Principal] = None) -> TaskRecord:
        t = self.repository.get_task(task_id)
        if not t:
            raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

        dep_state = self.recovery_service.check_dependencies_satisfied(task_id)
        if dep_state == "SATISFIED":
            return self.transition_task(task_id, TaskStatus.READY, reason=reason, principal=principal)
        else:
            return self.transition_task(task_id, TaskStatus.WAITING_DEPENDENCY, reason="Waiting for dependencies", principal=principal)

    def add_dependency(self, task_id: str, dependency_task_id: str, principal: Optional[Principal] = None) -> Any:
        self._authorize(principal, "filesystem.modify", f"task:{task_id}")
        self.repository.add_dependency(task_id, dependency_task_id)
        t = self.repository.get_task(task_id)
        if t and t.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.READY):
            self.transition_task(
                task_id=task_id,
                to_status=TaskStatus.WAITING_DEPENDENCY,
                reason=f"Added dependency '{dependency_task_id}'",
                principal=principal,
            )
        return AwaitableNone()

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        owner: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        parent_task_id: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        principal: Optional[Principal] = None,
    ) -> List[TaskRecord]:
        tasks = self.repository.list_tasks(
            status=status,
            priority=priority,
            owner=owner,
            task_type=task_type,
            parent_task_id=parent_task_id,
            assigned_agent_id=assigned_agent_id,
            correlation_id=correlation_id,
            limit=limit,
            offset=offset,
        )
        return AwaitableList(tasks)

    def get_task_history(self, task_id: str) -> List[TaskHistoryEntry]:
        return AwaitableList(self.repository.get_task_history(task_id))

    def get_history(self, task_id: str) -> List[TaskHistoryEntry]:
        return self.get_task_history(task_id)

    def handle_approval_decision(
        self,
        task_id: str,
        approval_id: str,
        decision: Any,
    ) -> Optional[TaskRecord]:
        """
        Synchronize task state when an approval decision (APPROVED, REJECTED, EXPIRED, CANCELLED) is recorded.
        """
        task = self.repository.get_task(task_id)
        if not task:
            return None

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return task

        dec_val = decision.value if hasattr(decision, "value") else str(decision)

        if dec_val == "APPROVED":
            if task.status in (TaskStatus.WAITING_APPROVAL, TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING):
                dep_state = self.recovery_service.check_dependencies_satisfied(task_id)
                to_status = TaskStatus.READY if dep_state == "SATISFIED" else TaskStatus.WAITING_DEPENDENCY
                return self.transition_task(
                    task_id=task_id,
                    to_status=to_status,
                    reason=f"Approval '{approval_id}' granted",
                    actor_id="approval_engine",
                )
        elif dec_val in ("REJECTED", "EXPIRED", "CANCELLED"):
            if task.status in (TaskStatus.WAITING_APPROVAL, TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.INTERRUPTED):
                if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                    self.transition_task(
                        task_id=task_id,
                        to_status=TaskStatus.INTERRUPTED,
                        reason=f"Approval '{approval_id}' {dec_val.lower()} during execution",
                        actor_id="approval_engine",
                    )
                target_status = (
                    TaskStatus.CANCELLED if dec_val == "CANCELLED" else (TaskStatus.FAILED if task.status == TaskStatus.INTERRUPTED else TaskStatus.BLOCKED)
                )
                return self.transition_task(
                    task_id=task_id,
                    to_status=target_status,
                    reason=f"Approval '{approval_id}' {dec_val.lower()}",
                    actor_id="approval_engine",
                )

        return task

    def recover_tasks(self) -> TaskRecoveryReport:
        return self.recovery_service.recover_tasks()

    async def health(self) -> HealthStatusContract:

        from jarvis.core.enums import HealthState

        return HealthStatusContract(
            component=self.name,
            status=HealthState.HEALTHY,
            error=None,
            metadata={"state": self._state},
        )
