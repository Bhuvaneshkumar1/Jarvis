"""
SQLite Persistent Repository for JARVIS Approvals and Policy State (Batch 15 & Batch 18).
Thread-safe, transaction-safe SQLite database integration using DatabaseManager / DatabaseSettings foundation.
"""

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import List, Optional, Any, Generator, Dict

from jarvis.database.settings import DatabaseSettings
from jarvis.database.migrations.runner import MigrationRunner
from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    ScopedApproval,
    PrincipalType,
    RiskLevel,
    ApprovalDecisionRecord,
    ApprovalHistoryEntry,
)
from jarvis.security.policy.exceptions import (
    ApprovalNotFoundError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalInvalidError,
    StaleApprovalVersionError,
    DuplicateDecisionError,
)
from jarvis.security.policy.state_machine import ApprovalStateMachine


class PolicyRepository:
    """
    Thread-safe SQLite persistent repository for approvals, approval decisions,
    approval history, scoped approvals, and policy state.

    Enforces atomic state transitions, optimistic concurrency versioning,
    deterministic queries with pagination, and restart-safe recovery.
    """

    def __init__(self, db_path: str = "data/jarvis.db", db_manager: Optional[Any] = None) -> None:
        self.db_path = db_path
        self.db_manager = db_manager
        self.settings = DatabaseSettings(db_path=self.db_path)
        self._lock = threading.Lock()

        if self.db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def _connection_scope(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock:
            with self._connection_scope() as conn:
                runner = MigrationRunner(settings=self.settings)
                runner.discover_and_apply_pending(conn)

    def _row_to_approval(self, row: sqlite3.Row) -> ApprovalRequest:
        d = dict(row)
        d["principal_type"] = PrincipalType(d["principal_type"])
        d["risk_level"] = RiskLevel(d["risk_level"])
        d["status"] = ApprovalStatus(d["status"])
        d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
        return ApprovalRequest(**d)

    def save_approval_request(self, req: ApprovalRequest) -> ApprovalRequest:
        """Persist a new approval request."""
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT approval_id FROM approvals WHERE approval_id = ?", (req.approval_id,))
                if cursor.fetchone():
                    raise ValueError(f"Approval with ID '{req.approval_id}' already exists.")

                req_fingerprint = req.request_fingerprint or req.operation_fingerprint
                now = req.created_at or time.time()

                cursor.execute(
                    """
                    INSERT INTO approvals (
                        approval_id, principal_id, principal_type, requested_action,
                        target_resource, exact_scope, risk_level, reason, task_id,
                        correlation_id, created_at, expires_at, status, approver_id,
                        decision_timestamp, decided_at, cancelled_at, decision_reason,
                        consumed_at, consumed_by_task_id, operation_fingerprint,
                        request_fingerprint, policy_version, version, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        req.approval_id,
                        req.principal_id,
                        req.principal_type.value,
                        req.requested_action,
                        req.target_resource,
                        req.exact_scope,
                        req.risk_level.value,
                        req.reason,
                        req.task_id,
                        req.correlation_id,
                        now,
                        req.expires_at,
                        req.status.value,
                        req.approver_id,
                        req.decision_timestamp or req.decided_at,
                        req.decided_at or req.decision_timestamp,
                        req.cancelled_at,
                        req.decision_reason,
                        req.consumed_at,
                        req.consumed_by_task_id,
                        req.operation_fingerprint,
                        req_fingerprint,
                        req.policy_version or "1.0.0",
                        req.version,
                        json.dumps(req.metadata),
                    ),
                )

                # Record initial history
                hist_id = f"hist-{os.urandom(6).hex()}"
                cursor.execute(
                    """
                    INSERT INTO approval_history (
                        history_id, approval_id, previous_status, new_status,
                        transition_reason, actor_id, timestamp, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hist_id,
                        req.approval_id,
                        None,
                        req.status.value,
                        "Approval request created",
                        req.principal_id,
                        now,
                        json.dumps({"task_id": req.task_id}),
                    ),
                )

                conn.commit()
                return req

    def get_approval_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                return self._row_to_approval(row) if row else None

    def get_approvals_by_task_id(self, task_id: str) -> List[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE task_id = ? ORDER BY created_at ASC", (task_id,))
                return [self._row_to_approval(row) for row in cursor.fetchall()]

    def get_approvals_by_requester(self, principal_id: str) -> List[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE principal_id = ? ORDER BY created_at ASC", (principal_id,))
                return [self._row_to_approval(row) for row in cursor.fetchall()]

    def list_pending_approvals(
        self,
        principal_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> List[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                query = "SELECT * FROM approvals WHERE status = ?"
                params: List[Any] = [ApprovalStatus.PENDING.value]
                if principal_id:
                    query += " AND principal_id = ?"
                    params.append(principal_id)
                if task_id:
                    query += " AND task_id = ?"
                    params.append(task_id)

                query += " ORDER BY created_at ASC"
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [self._row_to_approval(row) for row in cursor.fetchall()]

    def list_approvals_by_status(
        self,
        status: ApprovalStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC, approval_id ASC LIMIT ? OFFSET ?",
                    (status.value, limit, offset),
                )
                return [self._row_to_approval(row) for row in cursor.fetchall()]

    def list_approvals_in_time_range(
        self,
        start_time: float,
        end_time: float,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ApprovalRequest]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM approvals WHERE created_at >= ? AND created_at <= ? ORDER BY created_at ASC, approval_id ASC LIMIT ? OFFSET ?",
                    (start_time, end_time, limit, offset),
                )
                return [self._row_to_approval(row) for row in cursor.fetchall()]

    def update_approval_status(
        self,
        approval_id: str,
        new_status: ApprovalStatus,
        approver_id: Optional[str] = None,
        reason: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        Transactional status update with state machine validation and optimistic concurrency control.
        """
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                if not row:
                    raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

                current_approval = self._row_to_approval(row)
                current_status = current_approval.status
                current_version = current_approval.version

                # Version check
                if expected_version is not None and expected_version != current_version:
                    raise StaleApprovalVersionError(
                        f"Stale version for approval '{approval_id}': expected {expected_version}, current {current_version}."
                    )

                # State machine transition check
                ApprovalStateMachine.validate_transition(current_status, new_status)

                now = time.time()
                new_version = current_version + 1
                decided_at = current_approval.decided_at
                cancelled_at = current_approval.cancelled_at

                if new_status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
                    decided_at = now
                elif new_status == ApprovalStatus.CANCELLED:
                    cancelled_at = now

                cursor.execute(
                    """
                    UPDATE approvals SET
                        status = ?, approver_id = ?, decision_timestamp = ?,
                        decided_at = ?, cancelled_at = ?, decision_reason = ?,
                        version = ?
                    WHERE approval_id = ? AND version = ?
                    """,
                    (
                        new_status.value,
                        approver_id or current_approval.approver_id,
                        decided_at,
                        decided_at,
                        cancelled_at,
                        reason or current_approval.decision_reason,
                        new_version,
                        approval_id,
                        current_version,
                    ),
                )

                if cursor.rowcount == 0:
                    raise StaleApprovalVersionError(f"Optimistic lock conflict updating approval '{approval_id}'.")

                # Insert decision record if terminal decision
                if new_status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED):
                    dec_id = f"decrec-{os.urandom(6).hex()}"
                    cursor.execute(
                        """
                        INSERT INTO approval_decisions (
                            decision_id, approval_id, approver_id, decision,
                            decision_reason, decided_at, version_at_decision, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            dec_id,
                            approval_id,
                            approver_id or "system",
                            new_status.value,
                            reason,
                            now,
                            new_version,
                            json.dumps({}),
                        ),
                    )

                # Insert history entry
                hist_id = f"hist-{os.urandom(6).hex()}"
                cursor.execute(
                    """
                    INSERT INTO approval_history (
                        history_id, approval_id, previous_status, new_status,
                        transition_reason, actor_id, timestamp, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hist_id,
                        approval_id,
                        current_status.value,
                        new_status.value,
                        reason or f"Transitioned to {new_status.value}",
                        approver_id or "system",
                        now,
                        json.dumps({}),
                    ),
                )

                conn.commit()

        updated = self.get_approval_request(approval_id)
        if not updated:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' missing post update.")
        return updated

    def consume_approval_atomically(
        self,
        approval_id: str,
        consumer_task_id: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Atomically consume an APPROVED request.
        """
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                if not row:
                    raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

                curr = self._row_to_approval(row)
                now = time.time()

                if now >= curr.expires_at:
                    self.update_approval_status(approval_id, ApprovalStatus.EXPIRED, reason="Expired prior to consumption")
                    raise ApprovalExpiredError(f"Approval '{approval_id}' expired at {curr.expires_at}.")

                if curr.status == ApprovalStatus.CONSUMED:
                    raise ApprovalAlreadyConsumedError(f"Approval '{approval_id}' has already been consumed.")

                if curr.status != ApprovalStatus.APPROVED:
                    raise ApprovalInvalidError(f"Cannot consume approval '{approval_id}' in state '{curr.status.value}'. Must be APPROVED.")

                new_version = curr.version + 1
                cursor.execute(
                    """
                    UPDATE approvals SET status = ?, consumed_at = ?, consumed_by_task_id = ?, version = ?
                    WHERE approval_id = ? AND version = ? AND status = ?
                    """,
                    (
                        ApprovalStatus.CONSUMED.value,
                        now,
                        consumer_task_id,
                        new_version,
                        approval_id,
                        curr.version,
                        ApprovalStatus.APPROVED.value,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ApprovalAlreadyConsumedError(f"Concurrent consumption lock failed for approval '{approval_id}'.")

                hist_id = f"hist-{os.urandom(6).hex()}"
                cursor.execute(
                    """
                    INSERT INTO approval_history (
                        history_id, approval_id, previous_status, new_status,
                        transition_reason, actor_id, timestamp, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hist_id,
                        approval_id,
                        ApprovalStatus.APPROVED.value,
                        ApprovalStatus.CONSUMED.value,
                        "Consumed by task execution",
                        consumer_task_id or "task",
                        now,
                        json.dumps({"consumed_by_task_id": consumer_task_id}),
                    ),
                )
                conn.commit()

        updated = self.get_approval_request(approval_id)
        if not updated:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' missing post consumption.")
        return updated

    def get_approval_history(self, approval_id: str) -> List[ApprovalHistoryEntry]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM approval_history WHERE approval_id = ? ORDER BY timestamp ASC",
                    (approval_id,),
                )
                res = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["previous_status"] = ApprovalStatus(d["previous_status"]) if d.get("previous_status") else None
                    d["new_status"] = ApprovalStatus(d["new_status"])
                    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                    res.append(ApprovalHistoryEntry(**d))
                return res

    def get_approval_decisions(self, approval_id: str) -> List[ApprovalDecisionRecord]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM approval_decisions WHERE approval_id = ? ORDER BY decided_at ASC",
                    (approval_id,),
                )
                res = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["decision"] = ApprovalStatus(d["decision"])
                    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                    res.append(ApprovalDecisionRecord(**d))
                return res

    def record_decision(self, record: ApprovalDecisionRecord) -> ApprovalDecisionRecord:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT decision_id FROM approval_decisions WHERE decision_id = ?", (record.decision_id,))
                if cursor.fetchone():
                    raise DuplicateDecisionError(f"Decision record '{record.decision_id}' already exists.")

                cursor.execute(
                    """
                    INSERT INTO approval_decisions (
                        decision_id, approval_id, approver_id, decision,
                        decision_reason, decided_at, version_at_decision, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.decision_id,
                        record.approval_id,
                        record.approver_id,
                        record.decision.value,
                        record.decision_reason,
                        record.decided_at,
                        record.version_at_decision,
                        json.dumps(record.metadata),
                    ),
                )
                conn.commit()
                return record

    def expire_outdated_approvals(self, now: Optional[float] = None) -> List[ApprovalRequest]:
        """
        Idempotent expiry of overdue pending approvals.
        Returns the list of approval requests transitioned to EXPIRED.
        """
        current_time = now if now is not None else time.time()
        expired_records: List[ApprovalRequest] = []

        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM approvals WHERE status = ? AND expires_at <= ?",
                    (ApprovalStatus.PENDING.value, current_time),
                )
                pending_expired_rows = cursor.fetchall()

                for row in pending_expired_rows:
                    appr = self._row_to_approval(row)
                    new_version = appr.version + 1
                    cursor.execute(
                        """
                        UPDATE approvals SET status = ?, decision_reason = ?, version = ?
                        WHERE approval_id = ? AND version = ? AND status = ?
                        """,
                        (
                            ApprovalStatus.EXPIRED.value,
                            f"Expired at threshold {appr.expires_at}",
                            new_version,
                            appr.approval_id,
                            appr.version,
                            ApprovalStatus.PENDING.value,
                        ),
                    )
                    if cursor.rowcount > 0:
                        hist_id = f"hist-{os.urandom(6).hex()}"
                        cursor.execute(
                            """
                            INSERT INTO approval_history (
                                history_id, approval_id, previous_status, new_status,
                                transition_reason, actor_id, timestamp, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                hist_id,
                                appr.approval_id,
                                ApprovalStatus.PENDING.value,
                                ApprovalStatus.EXPIRED.value,
                                "Automatic expiry during maintenance/startup recovery",
                                "system",
                                current_time,
                                json.dumps({"expires_at": appr.expires_at}),
                            ),
                        )
                        appr_dict = appr.model_dump()
                        appr_dict["status"] = ApprovalStatus.EXPIRED
                        appr_dict["version"] = new_version
                        expired_records.append(ApprovalRequest(**appr_dict))

                conn.commit()
        return expired_records

    def save_scoped_approval(self, scoped: ScopedApproval) -> ScopedApproval:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO scoped_approvals (
                        approval_id, principal_id, principal_type_class, task_id,
                        allowed_actions, allowed_resources, max_risk_level, expires_at,
                        delegation_permitted, max_uses, used_count, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scoped.approval_id,
                        scoped.principal_id,
                        scoped.principal_type_class,
                        scoped.task_id,
                        json.dumps(scoped.allowed_actions),
                        json.dumps(scoped.allowed_resources),
                        scoped.max_risk_level.value,
                        scoped.expires_at,
                        1 if scoped.delegation_permitted else 0,
                        scoped.max_uses,
                        scoped.used_count,
                        scoped.created_at,
                        json.dumps(scoped.metadata),
                    ),
                )
                conn.commit()
                return scoped

    def get_valid_scoped_approvals(self, principal_id: str, task_id: Optional[str] = None) -> List[ScopedApproval]:
        now = time.time()
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM scoped_approvals WHERE principal_id = ? AND expires_at > ?"
                params: List[Any] = [principal_id, now]

                cursor.execute(query, params)
                res = []
                for row in cursor.fetchall():
                    d = dict(row)
                    if d["max_uses"] is not None and d["used_count"] >= d["max_uses"]:
                        continue
                    d["allowed_actions"] = json.loads(d["allowed_actions"])
                    d["allowed_resources"] = json.loads(d["allowed_resources"])
                    d["max_risk_level"] = RiskLevel(d["max_risk_level"])
                    d["delegation_permitted"] = bool(d["delegation_permitted"])
                    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                    res.append(ScopedApproval(**d))
                return res

    def increment_scoped_approval_usage(self, approval_id: str) -> None:
        with self._lock:
            with self._connection_scope() as conn:
                conn.execute("UPDATE scoped_approvals SET used_count = used_count + 1 WHERE approval_id = ?", (approval_id,))
                conn.commit()
