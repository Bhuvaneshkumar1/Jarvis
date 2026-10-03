"""
Working Memory Database Repository (Batch 25).
Extends BaseRepository to provide transactional persistence, indexed queries, optimistic locking, and scope isolation.
"""

import json
import sqlite3
import time
from typing import List, Optional, Dict, Any

from jarvis.database.repositories.base import BaseRepository
from jarvis.core.enums import MemoryScope, SecurityLevel
from jarvis.memory.working.models import (
    WorkingMemoryEntry,
    MemoryStatus,
    MemoryRetrievalFilter,
    MemoryStatistics,
)
from jarvis.memory.working.exceptions import (
    MemoryNotFoundError,
    MemoryConcurrencyError,
    MemoryAccessDeniedError,
)


class WorkingMemoryRepository(BaseRepository):
    """
    Relational SQLite Repository for Working Memory Persistence.
    Uses parameterized SQL queries, transaction scopes, and optimistic concurrency.
    """

    def _row_to_entry(self, row: sqlite3.Row) -> WorkingMemoryEntry:
        raw_meta = row["metadata"]
        try:
            metadata_dict = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            metadata_dict = {}

        return WorkingMemoryEntry(
            memory_id=row["memory_id"],
            scope=MemoryScope(row["scope"]),
            owner_id=row["owner_id"],
            conversation_id=row["conversation_id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            content=row["content"],
            content_type=row["content_type"],
            classification=SecurityLevel(row["classification"]),
            priority=row["priority"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            version=row["version"],
            source=row["source"],
            metadata=metadata_dict,
            status=MemoryStatus(row["status"]),
        )

    def create(self, entry: WorkingMemoryEntry) -> WorkingMemoryEntry:
        """Atomically persist a new working memory entry."""
        sql = """
            INSERT INTO working_memories (
                memory_id, scope, owner_id, conversation_id, task_id, agent_id,
                content, content_type, classification, priority, created_at, updated_at,
                expires_at, version, source, metadata, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        meta_json = json.dumps(entry.metadata)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    entry.memory_id,
                    entry.scope.value,
                    entry.owner_id,
                    entry.conversation_id,
                    entry.task_id,
                    entry.agent_id,
                    entry.content,
                    entry.content_type,
                    entry.classification.value,
                    entry.priority,
                    entry.created_at,
                    entry.updated_at,
                    entry.expires_at,
                    entry.version,
                    entry.source,
                    meta_json,
                    entry.status.value,
                ),
            )
            conn.commit()
        return entry

    def get_by_id(self, memory_id: str) -> Optional[WorkingMemoryEntry]:
        """Fetch a working memory entry by primary key."""
        sql = """
            SELECT memory_id, scope, owner_id, conversation_id, task_id, agent_id,
                   content, content_type, classification, priority, created_at, updated_at,
                   expires_at, version, source, metadata, status
            FROM working_memories
            WHERE memory_id = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (memory_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def update(self, entry: WorkingMemoryEntry) -> WorkingMemoryEntry:
        """
        Update an existing working memory entry using optimistic concurrency control.
        Increments the version number by 1.
        """
        now = time.time()
        new_version = entry.version + 1
        sql = """
            UPDATE working_memories
            SET scope = ?, owner_id = ?, conversation_id = ?, task_id = ?, agent_id = ?,
                content = ?, content_type = ?, classification = ?, priority = ?,
                updated_at = ?, expires_at = ?, version = ?, metadata = ?, status = ?
            WHERE memory_id = ? AND version = ?
        """
        meta_json = json.dumps(entry.metadata)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    entry.scope.value,
                    entry.owner_id,
                    entry.conversation_id,
                    entry.task_id,
                    entry.agent_id,
                    entry.content,
                    entry.content_type,
                    entry.classification.value,
                    entry.priority,
                    now,
                    entry.expires_at,
                    new_version,
                    meta_json,
                    entry.status.value,
                    entry.memory_id,
                    entry.version,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                # Determine if entry exists or version mismatch occurred
                existing = self.get_by_id(entry.memory_id)
                if not existing:
                    raise MemoryNotFoundError(f"Working memory entry '{entry.memory_id}' not found.")
                raise MemoryConcurrencyError(
                    f"Concurrency version mismatch for memory '{entry.memory_id}'. Expected version {entry.version}, found {existing.version}."
                )

        updated_entry = entry.model_copy()
        updated_entry.version = new_version
        updated_entry.updated_at = now
        return updated_entry

    def delete(
        self,
        memory_id: str,
        hard_delete: bool = False,
        owner_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a memory entry by ID. Soft-delete by default, or hard-delete if requested.
        Enforces ownership authorization if owner_id is provided.
        """
        existing = self.get_by_id(memory_id)
        if not existing:
            return False

        if owner_id and existing.owner_id != owner_id:
            raise MemoryAccessDeniedError(f"Owner '{owner_id}' is not authorized to delete memory '{memory_id}'.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if hard_delete:
                cursor.execute("DELETE FROM working_memories WHERE memory_id = ?", (memory_id,))
            else:
                now = time.time()
                cursor.execute(
                    "UPDATE working_memories SET status = ?, updated_at = ? WHERE memory_id = ?",
                    (MemoryStatus.DELETED.value, now, memory_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def clear_scope(
        self,
        scope: MemoryScope,
        owner_id: str,
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        hard_delete: bool = False,
    ) -> int:
        """
        Clear all memory entries belonging to a given scope and owner.
        Safely isolates clearing to specified sub-identifiers.
        """
        conditions = ["scope = ?", "owner_id = ?"]
        params: List[Any] = [scope.value, owner_id]

        if conversation_id:
            conditions.append("conversation_id = ?")
            params.append(conversation_id)
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where_clause = " AND ".join(conditions)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if hard_delete:
                sql = f"DELETE FROM working_memories WHERE {where_clause}"  # nosec B608
            else:
                now = time.time()
                sql = f"UPDATE working_memories SET status = ?, updated_at = ? WHERE {where_clause}"  # nosec B608
                params.insert(0, now)
                params.insert(0, MemoryStatus.DELETED.value)

            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount

    def list_memories(self, filter: MemoryRetrievalFilter) -> List[WorkingMemoryEntry]:
        """
        Retrieve memory entries matching filter parameters.
        Returns entries ordered by priority DESC and created_at DESC.
        """
        now = time.time()
        conditions = ["owner_id = ?"]
        params: List[Any] = [filter.owner_id]

        if filter.scopes:
            placeholders = ",".join(["?"] * len(filter.scopes))
            conditions.append(f"scope IN ({placeholders})")
            params.extend([s.value for s in filter.scopes])

        if filter.conversation_id:
            conditions.append("(conversation_id = ? OR conversation_id IS NULL)")
            params.append(filter.conversation_id)

        if filter.task_id:
            conditions.append("(task_id = ? OR task_id IS NULL)")
            params.append(filter.task_id)

        if filter.agent_id:
            conditions.append("(agent_id = ? OR agent_id IS NULL)")
            params.append(filter.agent_id)

        if filter.active_only:
            conditions.append("status = ?")
            params.append(MemoryStatus.ACTIVE.value)

        if filter.exclude_expired:
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)

        if filter.min_priority > 1:
            conditions.append("priority >= ?")
            params.append(filter.min_priority)

        if filter.content_type:
            conditions.append("content_type = ?")
            params.append(filter.content_type)

        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT memory_id, scope, owner_id, conversation_id, task_id, agent_id,
                   content, content_type, classification, priority, created_at, updated_at,
                   expires_at, version, source, metadata, status
            FROM working_memories
            WHERE {where_clause}
            ORDER BY priority DESC, created_at DESC
            LIMIT ?
        """  # nosec B608
        params.append(filter.limit * 2)  # Over-fetch slightly for subsequent scoring/budgeting

        entries: List[WorkingMemoryEntry] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                entries.append(self._row_to_entry(row))

        return entries

    def expire_memories(self, now: Optional[float] = None) -> int:
        """Mark all expired active entries as EXPIRED."""
        current_time = now if now is not None else time.time()
        sql = """
            UPDATE working_memories
            SET status = ?, updated_at = ?
            WHERE expires_at IS NOT NULL AND expires_at <= ? AND status = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (MemoryStatus.EXPIRED.value, current_time, current_time, MemoryStatus.ACTIVE.value))
            conn.commit()
            return cursor.rowcount

    def get_statistics(self, owner_id: Optional[str] = None) -> MemoryStatistics:
        """Calculate working memory statistics and breakdown."""
        where_clause = "WHERE owner_id = ?" if owner_id else ""
        params = [owner_id] if owner_id else []

        sql_counts = f"""
            SELECT status, scope, COUNT(*) as cnt, SUM(LENGTH(content)) as bytes
            FROM working_memories
            {where_clause}
            GROUP BY status, scope
        """  # nosec B608
        total = 0
        active = 0
        expired = 0
        deleted = 0
        total_bytes = 0
        by_scope: Dict[str, int] = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_counts, params)
            for row in cursor.fetchall():
                st = row["status"]
                sc = row["scope"]
                c = row["cnt"]
                b = row["bytes"] or 0

                total += c
                total_bytes += b
                by_scope[sc] = by_scope.get(sc, 0) + c

                if st == MemoryStatus.ACTIVE.value:
                    active += c
                elif st == MemoryStatus.EXPIRED.value:
                    expired += c
                elif st == MemoryStatus.DELETED.value:
                    deleted += c

        return MemoryStatistics(
            total_memories=total,
            active_memories=active,
            expired_memories=expired,
            deleted_memories=deleted,
            memories_by_scope=by_scope,
            total_content_bytes=total_bytes,
        )
