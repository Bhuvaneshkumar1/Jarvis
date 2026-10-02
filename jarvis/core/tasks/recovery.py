"""
Task Restart Recovery & Dependency Re-validation Service for JARVIS (Batch 17).
Identifies interrupted tasks on process startup, re-evaluates dependencies and approvals, and restores safe execution state.
"""

import logging
from typing import Optional, List, Any
from jarvis.core.enums import TaskStatus
from jarvis.core.tasks.contracts import TaskRecord, TaskRecoveryReport
from jarvis.core.tasks.repository import TaskRepository


class TaskRecoveryService:
    """
    Authoritative Task Restart Recovery Service.
    Safe, idempotent startup recovery of non-terminal tasks.
    """

    def __init__(
        self,
        repository: TaskRepository,
        policy_engine: Optional[Any] = None,
        approval_engine: Optional[Any] = None,
    ) -> None:
        self.repository = repository
        self.policy_engine = policy_engine
        self.approval_engine = approval_engine
        self.logger = logging.getLogger("TaskRecoveryService")

    def check_dependencies_satisfied(self, task_id: str) -> str:
        """
        Check dependency status for a task.
        Returns 'SATISFIED', 'BLOCKED', or 'PENDING'.
        """
        deps = self.repository.get_dependencies(task_id)
        if not deps:
            return "SATISFIED"

        for dep_id in deps:
            dep_task = self.repository.get_task(dep_id)
            if not dep_task:
                return "BLOCKED"

            if dep_task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED):
                return "BLOCKED"

            if dep_task.status != TaskStatus.COMPLETED:
                return "PENDING"

        return "SATISFIED"

    def recover_tasks(self) -> TaskRecoveryReport:
        """
        Idempotent startup task recovery process:
        - Interrupted RUNNING tasks -> RETRY_PENDING or FAILED
        - CANCELLING tasks -> CANCELLED
        - WAITING_DEPENDENCY tasks -> READY or BLOCKED
        - WAITING_APPROVAL tasks -> READY or BLOCKED
        """
        report = TaskRecoveryReport()
        non_terminal_statuses = [
            TaskStatus.RUNNING,
            TaskStatus.PAUSED,
            TaskStatus.CANCELLING,
            TaskStatus.WAITING_DEPENDENCY,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.QUEUED,
            TaskStatus.PENDING,
            TaskStatus.INTERRUPTED,
        ]

        tasks_to_check: List[TaskRecord] = []
        for status in non_terminal_statuses:
            tasks_to_check.extend(self.repository.list_tasks(status=status, limit=1000))

        report.total_inspected = len(tasks_to_check)

        for task in tasks_to_check:
            try:
                # 1. Interrupted RUNNING / INTERRUPTED tasks -> RETRY_PENDING or FAILED
                if task.status in (TaskStatus.RUNNING, TaskStatus.INTERRUPTED, TaskStatus.PAUSED):
                    if task.attempt_count < task.max_attempts:
                        updated = self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.RETRY_PENDING,
                            reason="Process restart recovery: execution interrupted, retry scheduled",
                            actor_id="recovery_service",
                        )
                        report.interrupted_marked_retry += 1
                        report.recovered_count += 1
                        report.recovered_tasks.append(updated)
                    else:
                        updated = self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.FAILED,
                            reason="Process restart recovery: maximum execution attempts reached",
                            actor_id="recovery_service",
                        )
                        report.interrupted_marked_failed += 1
                        report.recovered_count += 1
                        report.recovered_tasks.append(updated)

                # 2. CANCELLING tasks -> CANCELLED
                elif task.status == TaskStatus.CANCELLING:
                    updated = self.repository.transition_task(
                        task_id=task.task_id,
                        to_status=TaskStatus.CANCELLED,
                        reason="Process restart recovery: confirmed pending cancellation",
                        actor_id="recovery_service",
                    )
                    report.cancellation_confirmed += 1
                    report.recovered_count += 1
                    report.recovered_tasks.append(updated)

                # 3. WAITING_DEPENDENCY / QUEUED / PENDING tasks -> READY or BLOCKED
                elif task.status in (TaskStatus.WAITING_DEPENDENCY, TaskStatus.QUEUED, TaskStatus.PENDING):
                    dep_state = self.check_dependencies_satisfied(task.task_id)
                    if dep_state == "SATISFIED":
                        updated = self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.READY,
                            reason="Process restart recovery: dependencies satisfied",
                            actor_id="recovery_service",
                        )
                        report.recovered_count += 1
                        report.recovered_tasks.append(updated)
                    elif dep_state == "BLOCKED":
                        updated = self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.BLOCKED,
                            reason="Process restart recovery: prerequisite dependency failed or missing",
                            actor_id="recovery_service",
                        )
                        report.recovered_count += 1
                        report.recovered_tasks.append(updated)

                # 4. WAITING_APPROVAL tasks -> check approval
                elif task.status == TaskStatus.WAITING_APPROVAL and self.approval_engine:
                    pending_apprs = self.approval_engine.list_pending_approvals(task_id=task.task_id)
                    if not pending_apprs:
                        # Re-evaluate approval
                        updated = self.repository.transition_task(
                            task_id=task.task_id,
                            to_status=TaskStatus.BLOCKED,
                            reason="Process restart recovery: approval expired or unavailable",
                            actor_id="recovery_service",
                        )
                        report.recovered_count += 1
                        report.recovered_tasks.append(updated)

            except Exception as e:
                self.logger.error(f"Error recovering task '{task.task_id}': {str(e)}")

        return report
