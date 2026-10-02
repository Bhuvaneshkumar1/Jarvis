"""
SQLite Persistence Store for Recovery Executions, Lock Fencing, Outbox, and Integrity Checks (Batch 19).
Thread-safe, transaction-safe SQLite database integration using DatabaseSettings and MigrationRunner foundation.
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
from jarvis.core.recovery.models import (
    RecoveryRecord,
    RecoveryStatus,
    OutboxEventRecord,
)
from jarvis.core.exceptions import RecoveryLockError, RecoveryIntegrityError


class RecoveryRepository:
    """
    Thread-safe SQLite persistent repository for recovery state tracking,
    distributed recovery locks, fencing tokens, durable outbox queue, and integrity checks.
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
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL;")
            return conn
        except sqlite3.DatabaseError as e:
            raise RecoveryIntegrityError(f"Database corrupted: {str(e)}") from e

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

    # ---------------------------------------------------------
    # 1. Recovery Lock and Fencing Token Management
    # ---------------------------------------------------------

    def acquire_recovery_lock(
        self,
        lock_name: str = "system_startup_recovery",
        owner_id: str = "recovery_coordinator",
        ttl_seconds: float = 300.0,
    ) -> int:
        """
        Acquires a persistent recovery lock.
        Handles lock takeover if an existing lock expired (abandoned lock after process crash).
        Returns the new fencing_token integer.
        Raises RecoveryLockError if lock is active and owned by another process.
        """
        now = time.time()
        expires_at = now + ttl_seconds

        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM recovery_locks WHERE lock_name = ?", (lock_name,))
                row = cursor.fetchone()

                if not row:
                    # Initial lock creation
                    fencing_token = 1
                    cursor.execute(
                        """
                        INSERT INTO recovery_locks (lock_name, owner_id, acquired_at, expires_at, fencing_token)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (lock_name, owner_id, now, expires_at, fencing_token),
                    )
                    conn.commit()
                    return fencing_token

                existing_owner = row["owner_id"]
                existing_expires = row["expires_at"]
                current_token = row["fencing_token"]

                # If lock is held by same owner or expired, allow renewal / takeover with incremented token
                if existing_owner == owner_id or now >= existing_expires:
                    new_token = current_token + 1
                    cursor.execute(
                        """
                        UPDATE recovery_locks SET
                            owner_id = ?, acquired_at = ?, expires_at = ?, fencing_token = ?
                        WHERE lock_name = ?
                        """,
                        (owner_id, now, expires_at, new_token, lock_name),
                    )
                    conn.commit()
                    return int(new_token)

                raise RecoveryLockError(
                    f"Recovery lock '{lock_name}' is currently held by active owner '{existing_owner}' until {existing_expires} (current time: {now})."
                )

    def release_recovery_lock(
        self,
        lock_name: str = "system_startup_recovery",
        owner_id: str = "recovery_coordinator",
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Releases an owned recovery lock."""
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                if fencing_token is not None:
                    cursor.execute(
                        "DELETE FROM recovery_locks WHERE lock_name = ? AND owner_id = ? AND fencing_token = ?",
                        (lock_name, owner_id, fencing_token),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM recovery_locks WHERE lock_name = ? AND owner_id = ?",
                        (lock_name, owner_id),
                    )
                count = cursor.rowcount
                conn.commit()
                return count > 0

    # ---------------------------------------------------------
    # 2. Recovery Execution History Persistence
    # ---------------------------------------------------------

    def save_recovery_record(self, record: RecoveryRecord) -> RecoveryRecord:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO recovery_executions (
                        recovery_id, correlation_id, status, started_at, completed_at,
                        inspected_count, recovered_count, reconciled_count, failed_count,
                        manual_intervention_count, details
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.recovery_id,
                        record.correlation_id,
                        record.status.value,
                        record.started_at,
                        record.completed_at,
                        record.inspected_count,
                        record.recovered_count,
                        record.reconciled_count,
                        record.failed_count,
                        record.manual_intervention_count,
                        json.dumps(record.details),
                    ),
                )
                conn.commit()
                return record

    def update_recovery_record(self, record: RecoveryRecord) -> RecoveryRecord:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE recovery_executions SET
                        status = ?, completed_at = ?, inspected_count = ?,
                        recovered_count = ?, reconciled_count = ?, failed_count = ?,
                        manual_intervention_count = ?, details = ?
                    WHERE recovery_id = ?
                    """,
                    (
                        record.status.value,
                        record.completed_at or time.time(),
                        record.inspected_count,
                        record.recovered_count,
                        record.reconciled_count,
                        record.failed_count,
                        record.manual_intervention_count,
                        json.dumps(record.details),
                        record.recovery_id,
                    ),
                )
                conn.commit()
                return record

    def get_recovery_record(self, recovery_id: str) -> Optional[RecoveryRecord]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM recovery_executions WHERE recovery_id = ?", (recovery_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                d["status"] = RecoveryStatus(d["status"])
                d["details"] = json.loads(d["details"]) if d.get("details") else {}
                return RecoveryRecord(**d)

    # ---------------------------------------------------------
    # 3. Durable Outbox Queue Operations
    # ---------------------------------------------------------

    def enqueue_outbox_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> OutboxEventRecord:
        rec = OutboxEventRecord(
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            status="PENDING",
            created_at=time.time(),
        )
        with self._lock:
            with self._connection_scope() as conn:
                conn.execute(
                    """
                    INSERT INTO event_outbox (
                        event_id, event_type, payload, correlation_id, status,
                        created_at, dispatched_at, attempt_count, max_attempts, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.event_id,
                        rec.event_type,
                        json.dumps(rec.payload),
                        rec.correlation_id,
                        rec.status,
                        rec.created_at,
                        rec.dispatched_at,
                        rec.attempt_count,
                        rec.max_attempts,
                        rec.last_error,
                    ),
                )
                conn.commit()
                return rec

    def get_pending_outbox_events(self, limit: int = 100) -> List[OutboxEventRecord]:
        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM event_outbox WHERE status = 'PENDING' AND attempt_count < max_attempts ORDER BY created_at ASC LIMIT ?",
                    (limit,),
                )
                records = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["payload"] = json.loads(d["payload"]) if d.get("payload") else {}
                    records.append(OutboxEventRecord(**d))
                return records

    def mark_outbox_dispatched(self, event_id: str) -> None:
        now = time.time()
        with self._lock:
            with self._connection_scope() as conn:
                conn.execute(
                    "UPDATE event_outbox SET status = 'DISPATCHED', dispatched_at = ? WHERE event_id = ?",
                    (now, event_id),
                )
                conn.commit()

    def mark_outbox_failed(self, event_id: str, error_message: str) -> None:
        with self._lock:
            with self._connection_scope() as conn:
                conn.execute(
                    """
                    UPDATE event_outbox SET
                        attempt_count = attempt_count + 1,
                        last_error = ?,
                        status = CASE WHEN attempt_count + 1 >= max_attempts THEN 'FAILED' ELSE 'PENDING' END
                    WHERE event_id = ?
                    """,
                    (error_message, event_id),
                )
                conn.commit()

    # ---------------------------------------------------------
    # 4. Integrity Verification & Consistency Inspection
    # ---------------------------------------------------------

    def validate_database_integrity(self) -> Dict[str, Any]:
        """
        Executes safe database integrity checks on startup.
        Returns a diagnostic report of discovered inconsistencies and repair classifications.
        """
        report = {
            "orphaned_dependencies": 0,
            "corrupted_metadata_records": 0,
            "invalid_task_states": 0,
            "invalid_approval_states": 0,
            "fatal_corruption": False,
        }

        with self._lock:
            with self._connection_scope() as conn:
                cursor = conn.cursor()

                # Check 1: SQLite integrity check
                try:
                    cursor.execute("PRAGMA integrity_check;")
                    row = cursor.fetchone()
                    if row and row[0] != "ok":
                        report["fatal_corruption"] = True
                        raise RecoveryIntegrityError(f"Fatal SQLite Database Integrity Check Failed: {row[0]}")
                except sqlite3.DatabaseError as db_err:
                    report["fatal_corruption"] = True
                    raise RecoveryIntegrityError(f"Database corrupted: {db_err}") from db_err

                # Check 2: Orphaned task dependencies
                cursor.execute(
                    """
                    SELECT COUNT(*) as c FROM task_dependencies
                    WHERE task_id NOT IN (SELECT task_id FROM tasks)
                       OR dependency_task_id NOT IN (SELECT task_id FROM tasks)
                    """
                )
                report["orphaned_dependencies"] = cursor.fetchone()["c"]

                # Clean up orphaned task dependencies if any exist
                if report["orphaned_dependencies"] > 0:
                    cursor.execute(
                        """
                        DELETE FROM task_dependencies
                        WHERE task_id NOT IN (SELECT task_id FROM tasks)
                           OR dependency_task_id NOT IN (SELECT task_id FROM tasks)
                        """
                    )
                    conn.commit()

        return report
