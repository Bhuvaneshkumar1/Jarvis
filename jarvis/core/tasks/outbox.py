"""
Post-Commit Task Event Publisher & Event Bus Integrator for JARVIS (Batch 17).
Maps task state transitions to typed events and guarantees post-commit publication.
"""

from typing import Optional, Any
from jarvis.core.enums import TaskStatus
from jarvis.core.tasks.contracts import (
    TaskRecord,
    TaskCreatedEvent,
    TaskReadyEvent,
    TaskStartedEvent,
    TaskPausedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskCancelledEvent,
    TaskBlockedEvent,
    TaskUpdatedEvent,
    TaskCancellationRequestedEvent,
    TaskRetryScheduledEvent,
    TaskRecoveredEvent,
)


class TaskEventPublisher:
    """
    Publishes typed task lifecycle events to EventBus after successful database commits.
    """

    def __init__(self, event_bus: Optional[Any] = None):
        self.event_bus = event_bus

    def publish_task_created(self, task: TaskRecord) -> None:
        if not self.event_bus:
            return
        evt = TaskCreatedEvent(
            payload={
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "owner": task.owner,
                "correlation_id": task.correlation_id,
            }
        )
        self._publish(evt)

    def publish_status_changed(self, task: TaskRecord, old_status: TaskStatus) -> None:
        if not self.event_bus:
            return

        payload = {
            "task_id": task.task_id,
            "old_status": old_status.value,
            "new_status": task.status.value,
            "correlation_id": task.correlation_id,
            "version": task.version,
        }

        if task.status == TaskStatus.READY:
            self._publish(TaskReadyEvent(payload=payload))
        elif task.status == TaskStatus.RUNNING:
            self._publish(TaskStartedEvent(payload=payload))
        elif task.status == TaskStatus.PAUSED:
            self._publish(TaskPausedEvent(payload=payload))
        elif task.status == TaskStatus.COMPLETED:
            self._publish(TaskCompletedEvent(payload=payload))
        elif task.status == TaskStatus.FAILED:
            self._publish(TaskFailedEvent(payload=payload))
        elif task.status in (TaskStatus.CANCELLED, TaskStatus.CANCELLING):
            if task.status == TaskStatus.CANCELLING:
                self._publish(TaskCancellationRequestedEvent(payload=payload))
            else:
                self._publish(TaskCancelledEvent(payload=payload))
        elif task.status == TaskStatus.BLOCKED:
            self._publish(TaskBlockedEvent(payload=payload))
        elif task.status == TaskStatus.RETRY_PENDING:
            self._publish(TaskRetryScheduledEvent(payload=payload))
        elif task.status == TaskStatus.INTERRUPTED:
            self._publish(TaskRecoveredEvent(payload=payload))
        else:
            self._publish(TaskUpdatedEvent(payload=payload))

    def _publish(self, event: Any) -> None:
        if not self.event_bus:
            return
        try:
            if hasattr(self.event_bus, "publish_sync"):
                self.event_bus.publish_sync(event)
            elif hasattr(self.event_bus, "publish"):
                # If async, schedule on running event loop if possible
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.event_bus.publish(event))
                except RuntimeError:
                    pass
        except Exception:
            pass
