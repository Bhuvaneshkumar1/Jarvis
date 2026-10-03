"""
Expiration Manager for Working Memory Lifecycle (Batch 25).
Handles timestamp-based expiration checks, automatic state updates, and retention cleanup.
"""

import time
from typing import Optional
from jarvis.memory.working.models import WorkingMemoryEntry, MemoryStatus
from jarvis.memory.working.repository import WorkingMemoryRepository


class MemoryExpirationManager:
    """
    Manages working memory expiration enforcement and retention policy cleanup.
    """

    def is_expired(self, entry: WorkingMemoryEntry, now: Optional[float] = None) -> bool:
        """Evaluate if an entry has passed its expiration timestamp."""
        if entry.status == MemoryStatus.EXPIRED:
            return True
        if entry.expires_at is None:
            return False
        current_time = now if now is not None else time.time()
        return entry.expires_at <= current_time

    def check_and_expire(self, repository: WorkingMemoryRepository, now: Optional[float] = None) -> int:
        """Scan and update expired active memories in the repository."""
        return repository.expire_memories(now=now)

    def cleanup_expired(
        self,
        repository: WorkingMemoryRepository,
        retention_seconds: float = 86400 * 7,  # Default 7 days retention
        now: Optional[float] = None,
    ) -> int:
        """
        Hard-deletes expired or soft-deleted records older than retention threshold.
        """
        current_time = now if now is not None else time.time()
        cutoff_time = current_time - retention_seconds

        sql = """
            DELETE FROM working_memories
            WHERE status IN ('EXPIRED', 'DELETED') AND updated_at <= ?
        """
        with repository.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (cutoff_time,))
            conn.commit()
            return cursor.rowcount
