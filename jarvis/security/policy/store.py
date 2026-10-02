"""
SQLite Persistent Repository for JARVIS Approvals and Policy State (Batch 15).
"""

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import List, Optional, Any, Generator
from jarvis.security.policy.models import (
    ApprovalRequest,
    ApprovalStatus,
    ScopedApproval,
    PrincipalType,
    RiskLevel,
)
from jarvis.security.policy.exceptions import (
    ApprovalNotFoundError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalInvalidError,
)


class PolicyRepository:
    """
    Thread-safe SQLite persistent repository for approvals, scoped approvals, and policy audit logs.
    Enforces atomic state transitions and single-use approval consumption.
    """

    def __init__(self, db_path: str = "data/jarvis_policy.db") -> None:
        self.db_path = db_path
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
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS approvals (
                        approval_id TEXT PRIMARY KEY,
                        principal_id TEXT NOT NULL,
                        principal_type TEXT NOT NULL,
                        requested_action TEXT NOT NULL,
                        target_resource TEXT NOT NULL,
                        exact_scope TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        task_id TEXT,
                        correlation_id TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        status TEXT NOT NULL,
                        approver_id TEXT,
                        decision_timestamp REAL,
                        consumed_at REAL,
                        consumed_by_task_id TEXT,
                        operation_fingerprint TEXT,
                        metadata TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS scoped_approvals (
                        approval_id TEXT PRIMARY KEY,
                        principal_id TEXT NOT NULL,
                        principal_type_class TEXT,
                        task_id TEXT,
                        allowed_actions TEXT NOT NULL,
                        allowed_resources TEXT NOT NULL,
                        max_risk_level TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        delegation_permitted INTEGER NOT NULL DEFAULT 0,
                        max_uses INTEGER,
                        used_count INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        metadata TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS approval_audit_history (
                        history_id TEXT PRIMARY KEY,
                        approval_id TEXT NOT NULL,
                        from_status TEXT NOT NULL,
                        to_status TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        reason TEXT,
                        metadata TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
                    CREATE INDEX IF NOT EXISTS idx_approvals_principal ON approvals(principal_id);
                    CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);
                    CREATE INDEX IF NOT EXISTS idx_scoped_principal ON scoped_approvals(principal_id);
                    CREATE INDEX IF NOT EXISTS idx_scoped_task ON scoped_approvals(task_id);
                    """
                )
                conn.commit()

    def save_approval_request(self, req: ApprovalRequest) -> ApprovalRequest:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT approval_id FROM approvals WHERE approval_id = ?", (req.approval_id,))
                if cursor.fetchone():
                    raise ValueError(f"Approval with ID '{req.approval_id}' already exists.")

                cursor.execute(
                    """
                    INSERT INTO approvals (
                        approval_id, principal_id, principal_type, requested_action,
                        target_resource, exact_scope, risk_level, reason, task_id,
                        correlation_id, created_at, expires_at, status, approver_id,
                        decision_timestamp, consumed_at, consumed_by_task_id,
                        operation_fingerprint, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        req.created_at,
                        req.expires_at,
                        req.status.value,
                        req.approver_id,
                        req.decision_timestamp,
                        req.consumed_at,
                        req.consumed_by_task_id,
                        req.operation_fingerprint,
                        json.dumps(req.metadata),
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
                if not row:
                    return None
                d = dict(row)
                d["principal_type"] = PrincipalType(d["principal_type"])
                d["risk_level"] = RiskLevel(d["risk_level"])
                d["status"] = ApprovalStatus(d["status"])
                d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                return ApprovalRequest(**d)

    def list_pending_approvals(self, principal_id: Optional[str] = None, task_id: Optional[str] = None) -> List[ApprovalRequest]:
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
                res = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["principal_type"] = PrincipalType(d["principal_type"])
                    d["risk_level"] = RiskLevel(d["risk_level"])
                    d["status"] = ApprovalStatus(d["status"])
                    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                    res.append(ApprovalRequest(**d))
                return res

    def update_approval_status(
        self,
        approval_id: str,
        new_status: ApprovalStatus,
        approver_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                if not row:
                    raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

                current_status = ApprovalStatus(row["status"])
                now = time.time()

                if current_status in [ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED, ApprovalStatus.CONSUMED]:
                    raise ApprovalInvalidError(f"Cannot transition approval from terminal state '{current_status.value}'.")

                cursor.execute(
                    """
                    UPDATE approvals SET status = ?, approver_id = ?, decision_timestamp = ?
                    WHERE approval_id = ?
                    """,
                    (new_status.value, approver_id, now, approval_id),
                )
                conn.commit()

        req = self.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found after update.")
        return req

    def consume_approval_atomically(
        self,
        approval_id: str,
        consumer_task_id: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Atomically consume an APPROVED request in a single atomic SQL transaction.
        Fails if status is not APPROVED, or if already consumed/expired/rejected.
        """
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
                row = cursor.fetchone()
                if not row:
                    raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

                d = dict(row)
                status = ApprovalStatus(d["status"])
                expires_at = d["expires_at"]
                now = time.time()

                if now > expires_at:
                    cursor.execute("UPDATE approvals SET status = ? WHERE approval_id = ?", (ApprovalStatus.EXPIRED.value, approval_id))
                    conn.commit()
                    raise ApprovalExpiredError(f"Approval '{approval_id}' expired at {expires_at}.")

                if status == ApprovalStatus.CONSUMED:
                    raise ApprovalAlreadyConsumedError(f"Approval '{approval_id}' has already been consumed.")

                if status != ApprovalStatus.APPROVED:
                    raise ApprovalInvalidError(f"Cannot consume approval '{approval_id}' in state '{status.value}'. Must be APPROVED.")

                cursor.execute(
                    """
                    UPDATE approvals SET status = ?, consumed_at = ?, consumed_by_task_id = ?
                    WHERE approval_id = ? AND status = ?
                    """,
                    (ApprovalStatus.CONSUMED.value, now, consumer_task_id, approval_id, ApprovalStatus.APPROVED.value),
                )
                if cursor.rowcount == 0:
                    raise ApprovalAlreadyConsumedError(f"Concurrent consumption failed for approval '{approval_id}'.")
                conn.commit()

        req = self.get_approval_request(approval_id)
        if not req:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' missing post consumption.")
        return req

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

    def expire_outdated_approvals(self) -> int:
        now = time.time()
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE approvals SET status = ? WHERE status = ? AND expires_at <= ?",
                    (ApprovalStatus.EXPIRED.value, ApprovalStatus.PENDING.value, now),
                )
                count = cursor.rowcount
                conn.commit()
                return count
