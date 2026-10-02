"""
SQLite Persistent Repository for JARVIS Task Manager (Batch 6 & Batch 17).
Thread-safe, transaction-safe SQLite database integration using DatabaseManager foundation.
"""

import contextlib
import json
import os
import sqlite3
import threading
import time
from typing import List, Optional, Any, Generator
from jarvis.core.enums import TaskStatus, TaskPriority
from jarvis.core.tasks.contracts import TaskRecord, TaskHistoryEntry, TaskType
from jarvis.database.settings import DatabaseSettings
from jarvis.database.migrations.runner import MigrationRunner
from jarvis.core.tasks.exceptions import (
    TaskNotFoundError,
    TaskVersionConflictError,
    TaskDependencyError,
    TaskError,
    TaskDuplicateIdempotencyError,
)
from jarvis.core.tasks.state_machine import TaskStateMachine


class TaskRepository:
    """
    Thread-safe SQLite Persistent Task Repository.
    Manages task storage, dependencies, history, optimistic locking, idempotency keys, and restart recovery.
    """

    def __init__(self, db_path: str = "data/jarvis.db", db_manager: Optional[Any] = None) -> None:
        self.db_path = db_path
        self.db_manager = db_manager
        self._lock = threading.Lock()
        self.settings = DatabaseSettings(db_path=self.db_path)

        if self.db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                runner = MigrationRunner(settings=self.settings)
                runner.discover_and_apply_pending(conn)

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        d = dict(row)
        d["status"] = TaskStatus(d["status"])
        d["priority"] = TaskPriority(d["priority"])
        if d.get("task_type"):
            d["task_type"] = TaskType(d["task_type"])
        d["cancellation_requested"] = bool(d.get("cancellation_requested", 0))

        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                d["metadata"] = {}
        else:
            d["metadata"] = {}

        return TaskRecord(**d)

    def create_task(self, task: TaskRecord) -> TaskRecord:
        """Persist a new task record to database with idempotency check."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Idempotency Key check
                if task.idempotency_key:
                    cursor.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (task.idempotency_key,))
                    existing = cursor.fetchone()
                    if existing:
                        existing_task = self._row_to_task(existing)
                        # Payload match check
                        if existing_task.title != task.title or existing_task.owner != task.owner:
                            raise TaskDuplicateIdempotencyError(f"Idempotency key '{task.idempotency_key}' reused with conflicting task payload.")
                        return existing_task

                # 2. Task ID check
                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task.task_id,))
                if cursor.fetchone():
                    raise TaskError(f"Task with ID '{task.task_id}' already exists.")

                metadata_str = json.dumps(task.metadata)
                now = time.time()

                cursor.execute(
                    """
                    INSERT INTO tasks (
                        task_id, title, description, status, priority,
                        created_at, updated_at, started_at, completed_at, cancelled_at, failed_at,
                        owner, correlation_id, parent_task_id, metadata, version,
                        error_code, error_message, attempt_count, max_attempts,
                        task_type, idempotency_key, deadline_at, due_at, assigned_agent_id,
                        cancellation_requested, error_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.title,
                        task.description,
                        task.status.value,
                        task.priority.value,
                        task.created_at,
                        task.updated_at,
                        task.started_at,
                        task.completed_at,
                        task.cancelled_at,
                        task.failed_at,
                        task.owner,
                        task.correlation_id,
                        task.parent_task_id,
                        metadata_str,
                        task.version,
                        task.error_code,
                        task.error_message,
                        task.attempt_count,
                        task.max_attempts,
                        task.task_type.value,
                        task.idempotency_key,
                        task.deadline_at,
                        task.due_at,
                        task.assigned_agent_id,
                        1 if task.cancellation_requested else 0,
                        task.error_summary,
                    ),
                )

                # Record creation history entry
                hist_id = f"hist-{os.urandom(4).hex()}"
                cursor.execute(
                    """
                    INSERT INTO task_history (history_id, task_id, from_status, to_status, timestamp, reason, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (hist_id, task.task_id, "NONE", task.status.value, now, "Task created", "{}"),
                )

                conn.commit()
                return task

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                return self._row_to_task(row) if row else None

    def get_task_by_idempotency_key(self, idempotency_key: str) -> Optional[TaskRecord]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,))
                row = cursor.fetchone()
                return self._row_to_task(row) if row else None

    def update_task(self, task: TaskRecord, expected_version: Optional[int] = None) -> TaskRecord:
        """
        Update task record with optimistic concurrency control version checks.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version FROM tasks WHERE task_id = ?", (task.task_id,))
                row = cursor.fetchone()
                if not row:
                    raise TaskNotFoundError(f"Task ID '{task.task_id}' not found.")

                current_version = row["version"]
                if expected_version is not None and expected_version != current_version:
                    raise TaskVersionConflictError(f"Version conflict for task '{task.task_id}': expected {expected_version}, found {current_version}.")

                new_version = current_version + 1
                now = time.time()
                metadata_str = json.dumps(task.metadata)

                cursor.execute(
                    """
                    UPDATE tasks SET
                        title = ?, description = ?, status = ?, priority = ?,
                        updated_at = ?, started_at = ?, completed_at = ?, cancelled_at = ?, failed_at = ?,
                        owner = ?, correlation_id = ?, parent_task_id = ?, metadata = ?,
                        version = ?, error_code = ?, error_message = ?, attempt_count = ?, max_attempts = ?,
                        task_type = ?, idempotency_key = ?, deadline_at = ?, due_at = ?, assigned_agent_id = ?,
                        cancellation_requested = ?, error_summary = ?
                    WHERE task_id = ? AND version = ?
                    """,
                    (
                        task.title,
                        task.description,
                        task.status.value,
                        task.priority.value,
                        now,
                        task.started_at,
                        task.completed_at,
                        task.cancelled_at,
                        task.failed_at,
                        task.owner,
                        task.correlation_id,
                        task.parent_task_id,
                        metadata_str,
                        new_version,
                        task.error_code,
                        task.error_message,
                        task.attempt_count,
                        task.max_attempts,
                        task.task_type.value,
                        task.idempotency_key,
                        task.deadline_at,
                        task.due_at,
                        task.assigned_agent_id,
                        1 if task.cancellation_requested else 0,
                        task.error_summary,
                        task.task_id,
                        current_version,
                    ),
                )

                if cursor.rowcount == 0:
                    raise TaskVersionConflictError(f"Optimistic lock update failed for task '{task.task_id}'.")

                conn.commit()

                updated_dict = task.model_dump()
                updated_dict["version"] = new_version
                updated_dict["updated_at"] = now
                return TaskRecord(**updated_dict)

    def transition_task(
        self,
        task_id: str,
        to_status: TaskStatus,
        reason: str,
        actor_id: str = "system",
        expected_version: Optional[int] = None,
    ) -> TaskRecord:
        """
        Atomically transition task status, validate state machine, increment version, and record history entry.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                if not row:
                    raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

                current_task = self._row_to_task(row)
                from_status = current_task.status

                # State Machine Validation
                TaskStateMachine.validate_transition(task_id, from_status, to_status)

                if expected_version is not None and expected_version != current_task.version:
                    raise TaskVersionConflictError(f"Version conflict for task '{task_id}': expected {expected_version}, found {current_task.version}.")

                new_version = current_task.version + 1
                now = time.time()

                started_at = current_task.started_at
                completed_at = current_task.completed_at
                cancelled_at = current_task.cancelled_at
                failed_at = current_task.failed_at

                if to_status == TaskStatus.RUNNING and not started_at:
                    started_at = now
                elif to_status == TaskStatus.COMPLETED:
                    completed_at = now
                elif to_status in (TaskStatus.CANCELLED, TaskStatus.CANCELLING):
                    cancelled_at = now
                elif to_status == TaskStatus.FAILED:
                    failed_at = now

                cursor.execute(
                    """
                    UPDATE tasks SET
                        status = ?, updated_at = ?, started_at = ?, completed_at = ?,
                        cancelled_at = ?, failed_at = ?, version = ?
                    WHERE task_id = ? AND version = ?
                    """,
                    (
                        to_status.value,
                        now,
                        started_at,
                        completed_at,
                        cancelled_at,
                        failed_at,
                        new_version,
                        task_id,
                        current_task.version,
                    ),
                )

                if cursor.rowcount == 0:
                    raise TaskVersionConflictError(f"Optimistic lock update failed during transition for task '{task_id}'.")

                # Record history entry
                hist_id = f"hist-{os.urandom(4).hex()}"
                cursor.execute(
                    """
                    INSERT INTO task_history (history_id, task_id, from_status, to_status, timestamp, reason, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hist_id,
                        task_id,
                        from_status.value,
                        to_status.value,
                        now,
                        reason,
                        json.dumps({"actor_id": actor_id}),
                    ),
                )

                conn.commit()

                updated_dict = current_task.model_dump()
                updated_dict["status"] = to_status
                updated_dict["version"] = new_version
                updated_dict["updated_at"] = now
                updated_dict["started_at"] = started_at
                updated_dict["completed_at"] = completed_at
                updated_dict["cancelled_at"] = cancelled_at
                updated_dict["failed_at"] = failed_at
                return TaskRecord(**updated_dict)

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
    ) -> List[TaskRecord]:
        with self._lock:
            with self._get_connection() as conn:
                query = "SELECT * FROM tasks WHERE 1=1"
                params: List[Any] = []

                if status is not None:
                    query += " AND status = ?"
                    params.append(status.value)
                if priority is not None:
                    query += " AND priority = ?"
                    params.append(priority.value)
                if owner is not None:
                    query += " AND owner = ?"
                    params.append(owner)
                if task_type is not None:
                    query += " AND task_type = ?"
                    params.append(task_type.value)
                if parent_task_id is not None:
                    query += " AND parent_task_id = ?"
                    params.append(parent_task_id)
                if assigned_agent_id is not None:
                    query += " AND assigned_agent_id = ?"
                    params.append(assigned_agent_id)
                if correlation_id is not None:
                    query += " AND correlation_id = ?"
                    params.append(correlation_id)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor = conn.cursor()
                cursor.execute(query, params)
                return [self._row_to_task(row) for row in cursor.fetchall()]

    def add_dependency(self, task_id: str, dependency_task_id: str, dependency_type: str = "REQUIRED") -> None:
        if task_id == dependency_task_id:
            raise TaskDependencyError("Task cannot depend on itself.")

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,))
                if not cursor.fetchone():
                    raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (dependency_task_id,))
                if not cursor.fetchone():
                    raise TaskNotFoundError(f"Dependency Task ID '{dependency_task_id}' not found.")

                if self._check_path_exists(conn, dependency_task_id, task_id):
                    raise TaskDependencyError(f"Circular dependency detected between '{task_id}' and '{dependency_task_id}'.")

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO task_dependencies (task_id, dependency_task_id, dependency_type, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_id, dependency_task_id, dependency_type, time.time()),
                )
                conn.commit()

    def _check_path_exists(self, conn: sqlite3.Connection, start_id: str, target_id: str, visited: Optional[set] = None) -> bool:
        if start_id == target_id:
            return True
        if visited is None:
            visited = set()
        visited.add(start_id)

        cursor = conn.cursor()
        cursor.execute("SELECT dependency_task_id FROM task_dependencies WHERE task_id = ?", (start_id,))
        for row in cursor.fetchall():
            dep_id = row["dependency_task_id"]
            if dep_id not in visited:
                if self._check_path_exists(conn, dep_id, target_id, visited):
                    return True
        return False

    def get_dependencies(self, task_id: str) -> List[str]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT dependency_task_id FROM task_dependencies WHERE task_id = ?", (task_id,))
                return [row["dependency_task_id"] for row in cursor.fetchall()]

    def get_dependents(self, dependency_task_id: str) -> List[str]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT task_id FROM task_dependencies WHERE dependency_task_id = ?", (dependency_task_id,))
                return [row["task_id"] for row in cursor.fetchall()]

    def get_task_history(self, task_id: str) -> List[TaskHistoryEntry]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM task_history WHERE task_id = ? ORDER BY timestamp ASC", (task_id,))
                results = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
                    results.append(TaskHistoryEntry(**d))
                return results

    def record_history(self, entry: TaskHistoryEntry) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO task_history (history_id, task_id, from_status, to_status, timestamp, reason, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.history_id,
                        entry.task_id,
                        entry.from_status,
                        entry.to_status,
                        entry.timestamp,
                        entry.reason,
                        json.dumps(entry.metadata),
                    ),
                )
                conn.commit()

    def recover_tasks(self) -> List[TaskRecord]:
        """
        Startup Recovery: Inspect tasks left in non-terminal states.
        Transitions RUNNING/PAUSED tasks to INTERRUPTED cleanly.
        """
        recovered: List[TaskRecord] = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE status IN (?, ?)", (TaskStatus.RUNNING.value, TaskStatus.PAUSED.value))
                rows = cursor.fetchall()
                now = time.time()

                for row in rows:
                    t = self._row_to_task(row)
                    old_status = t.status.value
                    new_version = t.version + 1

                    cursor.execute(
                        """
                        UPDATE tasks SET status = ?, updated_at = ?, version = ?
                        WHERE task_id = ? AND version = ?
                        """,
                        (TaskStatus.INTERRUPTED.value, now, new_version, t.task_id, t.version),
                    )

                    hist_id = f"hist-{os.urandom(4).hex()}"
                    cursor.execute(
                        """
                        INSERT INTO task_history (history_id, task_id, from_status, to_status, timestamp, reason, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            hist_id,
                            t.task_id,
                            old_status,
                            TaskStatus.INTERRUPTED.value,
                            now,
                            "Process restart recovery: execution interrupted unexpectedly",
                            "{}",
                        ),
                    )

                    rec_dict = t.model_dump()
                    rec_dict["status"] = TaskStatus.INTERRUPTED
                    rec_dict["version"] = new_version
                    rec_dict["updated_at"] = now
                    recovered.append(TaskRecord(**rec_dict))

                conn.commit()
        return recovered
