"""
SQLite Persistent Repository for JARVIS Task Manager (Batch 6).
"""

import json
import os
import sqlite3
import threading
import time
from typing import List, Optional, Any
from jarvis.core.enums import TaskStatus, TaskPriority
from jarvis.core.tasks.contracts import TaskRecord, TaskHistoryEntry
from jarvis.core.exceptions import (
    TaskNotFoundError,
    TaskVersionConflictError,
    TaskDependencyError,
    TaskError,
)


class TaskRepository:
    """
    Thread-safe SQLite Persistent Task Repository.
    Manages task storage, dependencies, history, optimistic locking, and restart recovery.
    """

    def __init__(self, db_path: str = "data/jarvis_tasks.db") -> None:
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

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        started_at REAL,
                        completed_at REAL,
                        cancelled_at REAL,
                        failed_at REAL,
                        owner TEXT NOT NULL,
                        correlation_id TEXT NOT NULL,
                        parent_task_id TEXT,
                        metadata TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1,
                        error_code TEXT,
                        error_message TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3
                    );

                    CREATE TABLE IF NOT EXISTS task_dependencies (
                        task_id TEXT NOT NULL,
                        dependency_task_id TEXT NOT NULL,
                        dependency_type TEXT NOT NULL DEFAULT 'REQUIRED',
                        created_at REAL NOT NULL,
                        PRIMARY KEY (task_id, dependency_task_id)
                    );

                    CREATE TABLE IF NOT EXISTS task_history (
                        history_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        from_status TEXT NOT NULL,
                        to_status TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        reason TEXT,
                        metadata TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                    CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
                    CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
                    CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
                    CREATE INDEX IF NOT EXISTS idx_tasks_correlation ON tasks(correlation_id);
                    CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id);
                    """
                )
                conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        d = dict(row)
        d["status"] = TaskStatus(d["status"])
        d["priority"] = TaskPriority(d["priority"])
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                d["metadata"] = {}
        else:
            d["metadata"] = {}
        return TaskRecord(**d)

    def create_task(self, task: TaskRecord) -> TaskRecord:
        """Persist a new task record to database."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task.task_id,))
                if cursor.fetchone():
                    raise TaskError(f"Task with ID '{task.task_id}' already exists.")

                metadata_str = json.dumps(task.metadata)
                cursor.execute(
                    """
                    INSERT INTO tasks (
                        task_id, title, description, status, priority,
                        created_at, updated_at, started_at, completed_at, cancelled_at, failed_at,
                        owner, correlation_id, parent_task_id, metadata, version,
                        error_code, error_message, attempt_count, max_attempts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                conn.commit()
                return task

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Fetch task by ID from persistent database."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                return self._row_to_task(row) if row else None

    def update_task(self, task: TaskRecord, expected_version: Optional[int] = None) -> TaskRecord:
        """
        Update an existing task record with optimistic locking checks.
        Increments version by 1.
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
                        version = ?, error_code = ?, error_message = ?, attempt_count = ?, max_attempts = ?
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
                        task.task_id,
                        current_version,
                    ),
                )

                if cursor.rowcount == 0:
                    raise TaskVersionConflictError(f"Optimistic lock update failed for task '{task.task_id}'.")

                conn.commit()

                # Return updated task with incremented version & updated_at timestamp
                updated_dict = task.model_dump()
                updated_dict["version"] = new_version
                updated_dict["updated_at"] = now
                return TaskRecord(**updated_dict)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        owner: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskRecord]:
        """Query tasks with optional filtering and pagination."""
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
                if parent_task_id is not None:
                    query += " AND parent_task_id = ?"
                    params.append(parent_task_id)
                if correlation_id is not None:
                    query += " AND correlation_id = ?"
                    params.append(correlation_id)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor = conn.cursor()
                cursor.execute(query, params)
                return [self._row_to_task(row) for row in cursor.fetchall()]

    def add_dependency(self, task_id: str, dependency_task_id: str, dependency_type: str = "REQUIRED") -> None:
        """
        Add dependency relationship between task_id and dependency_task_id.
        Rejects self-dependency and circular dependencies.
        """
        if task_id == dependency_task_id:
            raise TaskDependencyError("Task cannot depend on itself.")

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Check task existence
                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,))
                if not cursor.fetchone():
                    raise TaskNotFoundError(f"Task ID '{task_id}' not found.")

                cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (dependency_task_id,))
                if not cursor.fetchone():
                    raise TaskNotFoundError(f"Dependency Task ID '{dependency_task_id}' not found.")

                # Cycle detection using DFS: can dependency_task_id reach task_id?
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
        """Get list of task IDs that task_id depends on."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT dependency_task_id FROM task_dependencies WHERE task_id = ?", (task_id,))
                return [row["dependency_task_id"] for row in cursor.fetchall()]

    def get_dependents(self, dependency_task_id: str) -> List[str]:
        """Get list of task IDs that depend on dependency_task_id."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT task_id FROM task_dependencies WHERE dependency_task_id = ?",
                    (dependency_task_id,),
                )
                return [row["task_id"] for row in cursor.fetchall()]

    def record_history(self, entry: TaskHistoryEntry) -> None:
        """Persist state audit history entry."""
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

    def get_history(self, task_id: str) -> List[TaskHistoryEntry]:
        """Fetch status history log entries for given task_id."""
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

    def recover_tasks(self) -> List[TaskRecord]:
        """
        Inspect persisted database on startup for tasks left in non-terminal states
        (RUNNING, PAUSED) and transition them to INTERRUPTED.
        """
        recovered: List[TaskRecord] = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE status IN (?, ?)", ("RUNNING", "PAUSED"))
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
                        ("INTERRUPTED", now, new_version, t.task_id, t.version),
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
                            "INTERRUPTED",
                            now,
                            "Process restart recovery: recovered after unexpected process restart",
                            "{}",
                        ),
                    )

                    rec_task = t.model_dump()
                    rec_task["status"] = TaskStatus.INTERRUPTED
                    rec_task["version"] = new_version
                    rec_task["updated_at"] = now
                    recovered.append(TaskRecord(**rec_task))

                conn.commit()
        return recovered
