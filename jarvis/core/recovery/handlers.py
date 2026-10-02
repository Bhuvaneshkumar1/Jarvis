"""
Specialized Handlers for Task, Approval, and Event Outbox Recovery (Batch 19).
"""

import logging
import time
from typing import Dict, Any, List, Optional

from jarvis.core.enums import TaskStatus
from jarvis.core.tasks.contracts import TaskRecord
from jarvis.core.tasks.repository import TaskRepository
from jarvis.security.policy.recovery import ApprovalRecoveryService
from jarvis.security.policy.store import PolicyRepository
from jarvis.core.recovery.models import OperationClassification
from jarvis.core.recovery.store import RecoveryRepository

logger = logging.getLogger(__name__)


class TaskRecoveryHandler:
    """
    Handler responsible for inspecting and reconciling persistent task state after process interruption or restart.
    """

    def __init__(
        self,
        task_repository: TaskRepository,
        policy_engine: Optional[Any] = None,
    ) -> None:
        self.repository = task_repository
        self.policy_engine = policy_engine

    def recover_tasks(self) -> Dict[str, Any]:
        """
        Inspects non-terminal tasks and applies state recovery rules.
        Returns a summary dict with recovery metrics.
        """
        inspected = 0
        recovered = 0
        reconciled = 0
        failed = 0
        manual_intervention = 0

        # Query non-terminal task states
        non_terminal_statuses = [
            TaskStatus.RUNNING,
            TaskStatus.PAUSED,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.WAITING_DEPENDENCY,
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
        ]

        tasks_to_inspect: List[TaskRecord] = []
        for st in non_terminal_statuses:
            tasks_to_inspect.extend(self.repository.list_tasks(status=st, limit=500))

        inspected = len(tasks_to_inspect)

        for task in tasks_to_inspect:
            try:
                classification = self._classify_task_operation(task)

                if classification == OperationClassification.REQUIRES_MANUAL_INTERVENTION:
                    if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                        self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.INTERRUPTED,
                            reason="Process restart recovery: operation requires manual intervention or reconciliation",
                            actor_id="recovery_handler",
                        )
                    manual_intervention += 1
                elif classification == OperationClassification.SAFE_TO_RETRY:
                    if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                        self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.INTERRUPTED,
                            reason="Process restart recovery: idempotent task interrupted",
                            actor_id="recovery_handler",
                        )
                    self.repository.transition_task(
                        task_id=task.task_id,
                        to_status=TaskStatus.READY,
                        reason="Process restart recovery: idempotent task ready to resume",
                        actor_id="recovery_handler",
                    )
                    recovered += 1
                elif classification == OperationClassification.CONFIRMED_NOT_EXECUTED:
                    if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                        self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.INTERRUPTED,
                            reason="Process restart recovery: execution interrupted cleanly",
                            actor_id="recovery_handler",
                        )
                        recovered += 1
                    else:
                        reconciled += 1
                else:
                    reconciled += 1

            except Exception as e:
                logger.error(f"Error recovering task '{task.task_id}': {e}")
                failed += 1

        return {
            "inspected_count": inspected,
            "recovered_count": recovered,
            "reconciled_count": reconciled,
            "failed_count": failed,
            "manual_intervention_count": manual_intervention,
        }

    def _classify_task_operation(self, task: TaskRecord) -> OperationClassification:
        """Classifies an interrupted task's side-effect safety."""
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.BLOCKED):
            return OperationClassification.CONFIRMED_EXECUTED

        # If task has an idempotency key, it is safe to retry
        if task.idempotency_key:
            return OperationClassification.SAFE_TO_RETRY

        # If task was actively running without idempotency guarantees and metadata indicates external side-effects
        meta = task.metadata or {}
        if task.status == TaskStatus.RUNNING and meta.get("has_external_side_effects"):
            return OperationClassification.REQUIRES_MANUAL_INTERVENTION

        return OperationClassification.CONFIRMED_NOT_EXECUTED


class ApprovalRecoveryHandler:
    """
    Handler responsible for recovering persistent approval lifecycle state and syncing linked tasks.
    """

    def __init__(
        self,
        policy_repository: PolicyRepository,
        task_manager: Optional[Any] = None,
    ) -> None:
        self.policy_repository = policy_repository
        self.task_manager = task_manager
        self.service = ApprovalRecoveryService(
            repository=self.policy_repository,
            task_manager=self.task_manager,
        )

    def recover_approvals(self, now: Optional[float] = None) -> Dict[str, Any]:
        current_time = now if now is not None else time.time()
        expired_records = self.service.recover_expired_approvals(now=current_time)

        return {
            "inspected_count": len(expired_records),
            "recovered_count": len(expired_records),
            "reconciled_count": len(expired_records),
            "failed_count": 0,
            "manual_intervention_count": 0,
            "expired_approval_ids": [r.approval_id for r in expired_records],
        }


class EventOutboxHandler:
    """
    Handler responsible for reconciling and dispatching pending outbox events across restarts.
    """

    def __init__(
        self,
        recovery_repository: RecoveryRepository,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.recovery_repository = recovery_repository
        self.event_bus = event_bus

    def reconcile_outbox(self) -> Dict[str, Any]:
        pending = self.recovery_repository.get_pending_outbox_events(limit=100)
        dispatched_count = 0
        failed_count = 0

        for evt in pending:
            if self.event_bus:
                try:
                    # Construct generic event object or pass payload
                    if hasattr(self.event_bus, "publish"):
                        # Re-publish event to bus
                        from jarvis.core.events.contracts import Event

                        generic_evt = Event(event_type=evt.event_type, payload=evt.payload)
                        self.event_bus.publish(generic_evt)

                    self.recovery_repository.mark_outbox_dispatched(evt.event_id)
                    dispatched_count += 1
                except Exception as e:
                    self.recovery_repository.mark_outbox_failed(evt.event_id, str(e))
                    failed_count += 1
            else:
                # If no event bus registered, leave pending in outbox for subsequent startup
                pass

        return {
            "inspected_count": len(pending),
            "recovered_count": dispatched_count,
            "reconciled_count": dispatched_count,
            "failed_count": failed_count,
            "manual_intervention_count": 0,
        }
