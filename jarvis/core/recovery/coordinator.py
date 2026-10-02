"""
Authoritative Centralized Recovery Coordinator for JARVIS (Batch 19).
Coordinates startup state recovery sequence, distributed locking, task recovery,
approval expiry recovery, event outbox reconciliation, and audit reporting.
"""

import logging
import os
import time
import uuid
from typing import Optional, Any

from jarvis.core.logging import JarvisLogger
from jarvis.core.audit_log import AuditLogger
from jarvis.core.exceptions import RecoveryIntegrityError
from jarvis.core.tasks.repository import TaskRepository
from jarvis.security.policy.store import PolicyRepository
from jarvis.core.recovery.models import RecoveryRecord, RecoveryStatus
from jarvis.core.recovery.store import RecoveryRepository
from jarvis.core.recovery.handlers import (
    TaskRecoveryHandler,
    ApprovalRecoveryHandler,
    EventOutboxHandler,
)

logger = logging.getLogger(__name__)


class RecoveryCoordinator:
    """
    Authoritative Central State Recovery Coordinator.
    Executes a deterministic, idempotent 16-step startup recovery sequence.
    """

    def __init__(
        self,
        recovery_repository: Optional[RecoveryRepository] = None,
        task_repository: Optional[TaskRepository] = None,
        policy_repository: Optional[PolicyRepository] = None,
        task_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        policy_engine: Optional[Any] = None,
        db_path: str = "data/jarvis.db",
        owner_id: Optional[str] = None,
    ) -> None:
        self.db_path = db_path
        self.recovery_repository = recovery_repository or RecoveryRepository(db_path=self.db_path)
        self.task_repository = task_repository or TaskRepository(db_path=self.db_path)
        self.policy_repository = policy_repository or PolicyRepository(db_path=self.db_path)
        self.task_manager = task_manager
        self.event_bus = event_bus
        self.policy_engine = policy_engine
        self.owner_id = owner_id or f"coordinator-{os.getpid()}-{uuid.uuid4().hex[:6]}"

        self.audit_logger = AuditLogger()
        self.jarvis_logger = JarvisLogger(component="RecoveryCoordinator")

        # Handlers
        self.task_handler = TaskRecoveryHandler(
            task_repository=self.task_repository,
            policy_engine=self.policy_engine,
        )
        self.approval_handler = ApprovalRecoveryHandler(
            policy_repository=self.policy_repository,
            task_manager=self.task_manager,
        )
        self.outbox_handler = EventOutboxHandler(
            recovery_repository=self.recovery_repository,
            event_bus=self.event_bus,
        )

    def execute_recovery(self, lock_ttl_seconds: float = 300.0) -> RecoveryRecord:
        """
        Executes the deterministic 16-step persistent state recovery workflow.
        Fails closed if critical database corruption or lock contention occurs.
        """
        correlation_id = f"corr-rec-{uuid.uuid4().hex[:8]}"
        self.jarvis_logger.info("Initiating JARVIS Persistent State Recovery Sequence...")

        # Step 1: Acquire recovery execution lock & fencing token
        fencing_token = self.recovery_repository.acquire_recovery_lock(
            lock_name="system_startup_recovery",
            owner_id=self.owner_id,
            ttl_seconds=lock_ttl_seconds,
        )

        record = RecoveryRecord(
            correlation_id=correlation_id,
            status=RecoveryStatus.INSPECTING,
            started_at=time.time(),
            details={"fencing_token": fencing_token, "owner_id": self.owner_id},
        )
        self.recovery_repository.save_recovery_record(record)

        try:
            # Step 2: Validate Database Integrity
            integrity_report = self.recovery_repository.validate_database_integrity()
            record.details["integrity_report"] = integrity_report

            if integrity_report.get("fatal_corruption"):
                record.status = RecoveryStatus.FAILED
                record.completed_at = time.time()
                self.recovery_repository.update_recovery_record(record)
                raise RecoveryIntegrityError("Fatal database corruption detected during startup recovery.")

            # Step 3: Transition to RECOVERING
            record.status = RecoveryStatus.RECOVERING
            self.recovery_repository.update_recovery_record(record)

            # Step 4: Approval Recovery (expire overdue pending approvals & sync tasks)
            appr_res = self.approval_handler.recover_approvals()

            # Step 5: Task State Recovery (reconcile interrupted non-terminal tasks)
            task_res = self.task_handler.recover_tasks()

            # Step 6: Transition to RECONCILING & Outbox Replay
            record.status = RecoveryStatus.RECONCILING
            self.recovery_repository.update_recovery_record(record)

            outbox_res = self.outbox_handler.reconcile_outbox()

            # Step 7: Aggregate Metrics & Metrics Summary
            record.inspected_count = appr_res["inspected_count"] + task_res["inspected_count"] + outbox_res["inspected_count"]
            record.recovered_count = appr_res["recovered_count"] + task_res["recovered_count"] + outbox_res["recovered_count"]
            record.reconciled_count = appr_res["reconciled_count"] + task_res["reconciled_count"] + outbox_res["reconciled_count"]
            record.failed_count = appr_res["failed_count"] + task_res["failed_count"] + outbox_res["failed_count"]
            record.manual_intervention_count = (
                appr_res["manual_intervention_count"] + task_res["manual_intervention_count"] + outbox_res["manual_intervention_count"]
            )

            # Step 8: Transition to VERIFYING & Determine Final Status
            record.status = RecoveryStatus.VERIFYING
            self.recovery_repository.update_recovery_record(record)

            if record.failed_count > 0:
                record.status = RecoveryStatus.FAILED
            elif record.manual_intervention_count > 0:
                record.status = RecoveryStatus.COMPLETED_WITH_WARNINGS
            else:
                record.status = RecoveryStatus.COMPLETED

            record.completed_at = time.time()
            self.recovery_repository.update_recovery_record(record)

            # Step 9: Audit Logging
            self.audit_logger.log_event(
                component="RecoveryCoordinator",
                action="STATE_RECOVERY",
                result=record.status.value,
                correlation_id=correlation_id,
                details={
                    "recovery_id": record.recovery_id,
                    "inspected": record.inspected_count,
                    "recovered": record.recovered_count,
                    "manual_intervention": record.manual_intervention_count,
                },
            )

            self.jarvis_logger.info(
                f"JARVIS Persistent State Recovery Completed: status={record.status.value}, "
                f"inspected={record.inspected_count}, recovered={record.recovered_count}, "
                f"manual_intervention={record.manual_intervention_count}."
            )

            return record

        except Exception as e:
            record.status = RecoveryStatus.FAILED
            record.completed_at = time.time()
            record.details["error"] = str(e)
            self.recovery_repository.update_recovery_record(record)
            self.jarvis_logger.error(f"State recovery failed: {e}")
            raise

        finally:
            # Step 10: Release Recovery Lock
            self.recovery_repository.release_recovery_lock(
                lock_name="system_startup_recovery",
                owner_id=self.owner_id,
                fencing_token=fencing_token,
            )
