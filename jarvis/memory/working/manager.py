"""
Centralized Working Memory Manager (Batch 25).
Coordinates CRUD operations, scope isolation, privacy policy checks, selective retrieval, token budgeting, and background cleanup.
"""

import time
from typing import List, Optional
from jarvis.database.manager import DatabaseManager
from jarvis.core.enums import MemoryScope
from jarvis.core.logging import JarvisLogger
from jarvis.memory.working.models import (
    WorkingMemoryEntry,
    MemoryRetrievalFilter,
    MemoryStatistics,
    MemoryStatus,
)
from jarvis.memory.working.repository import WorkingMemoryRepository
from jarvis.memory.working.retrieval import SelectiveMemoryRetrievalEngine
from jarvis.memory.working.prioritizer import MemoryPrioritizer
from jarvis.memory.working.token_budget import TokenBudgetManager
from jarvis.memory.working.expiration import MemoryExpirationManager
from jarvis.memory.working.exceptions import (
    MemoryValidationError,
    MemoryNotFoundError,
    MemoryAccessDeniedError,
)


class WorkingMemoryManager:
    """
    Authoritative Centralized Working Memory Manager.
    Enforces scope isolation, access control, atomic persistence, and context window limits.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        logger: Optional[JarvisLogger] = None,
    ):
        self.db_manager = db_manager
        self.logger = logger or JarvisLogger(component="WorkingMemoryManager")
        self.repository = WorkingMemoryRepository(db_manager=db_manager)
        self.prioritizer = MemoryPrioritizer()
        self.budget_manager = TokenBudgetManager()
        self.retrieval_engine = SelectiveMemoryRetrievalEngine(
            prioritizer=self.prioritizer,
            budget_manager=self.budget_manager,
        )
        self.expiration_manager = MemoryExpirationManager()

    def create(self, entry: WorkingMemoryEntry) -> WorkingMemoryEntry:
        """
        Create and persist a new working memory entry.
        """
        # Validate schema & expiration
        if entry.expires_at is not None and entry.expires_at <= time.time():
            raise MemoryValidationError(f"Cannot create working memory '{entry.memory_id}' with an expired timestamp.")

        # Persist entry via repository
        saved_entry = self.repository.create(entry)
        self.logger.info(f"Created working memory '{saved_entry.memory_id}' in scope '{saved_entry.scope.value}'.")
        return saved_entry

    def get(self, memory_id: str, requester_owner_id: str) -> Optional[WorkingMemoryEntry]:
        """
        Retrieve a working memory entry by ID.
        Verifies requester authorization and excludes expired/deleted entries.
        """
        entry = self.repository.get_by_id(memory_id)
        if not entry:
            return None

        # Exclude deleted entries
        if entry.status == MemoryStatus.DELETED:
            return None

        # Exclude expired entries
        if self.expiration_manager.is_expired(entry):
            return None

        # Security Isolation Check
        if entry.owner_id != requester_owner_id:
            raise MemoryAccessDeniedError(f"Requester '{requester_owner_id}' is not authorized to access memory '{memory_id}'.")

        return entry

    def update(self, entry: WorkingMemoryEntry, requester_owner_id: str) -> WorkingMemoryEntry:
        """
        Update an existing working memory entry.
        Verifies ownership and applies optimistic concurrency version checking.
        """
        existing = self.get(entry.memory_id, requester_owner_id=requester_owner_id)
        if not existing:
            raise MemoryNotFoundError(f"Working memory entry '{entry.memory_id}' not found or inaccessible.")

        if existing.owner_id != requester_owner_id:
            raise MemoryAccessDeniedError(f"Requester '{requester_owner_id}' is not authorized to update memory '{entry.memory_id}'.")

        return self.repository.update(entry)

    def delete(
        self,
        memory_id: str,
        requester_owner_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a working memory entry by ID.
        """
        return self.repository.delete(
            memory_id=memory_id,
            hard_delete=hard_delete,
            owner_id=requester_owner_id,
        )

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
        Clear working memory entries for a specific scope and owner.
        """
        cleared_count = self.repository.clear_scope(
            scope=scope,
            owner_id=owner_id,
            conversation_id=conversation_id,
            task_id=task_id,
            agent_id=agent_id,
            hard_delete=hard_delete,
        )
        self.logger.info(f"Cleared {cleared_count} memories from scope '{scope.value}' for owner '{owner_id}'.")
        return cleared_count

    def retrieve(self, filter: MemoryRetrievalFilter) -> List[WorkingMemoryEntry]:
        """
        Selectively retrieve working memories matching criteria and token budget.
        """
        # Ensure expired records are marked before retrieval
        self.expiration_manager.check_and_expire(self.repository)

        return self.retrieval_engine.retrieve(
            repository=self.repository,
            filter=filter,
        )

    def list_by_scope(
        self,
        scope: MemoryScope,
        owner_id: str,
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[WorkingMemoryEntry]:
        """
        List active memories matching scope and ownership parameters.
        """
        filter = MemoryRetrievalFilter(
            scopes=[scope],
            owner_id=owner_id,
            conversation_id=conversation_id,
            task_id=task_id,
            agent_id=agent_id,
            limit=limit,
        )
        return self.retrieve(filter)

    def expire(self, now: Optional[float] = None) -> int:
        """Trigger background expiration sweep."""
        return self.expiration_manager.check_and_expire(self.repository, now=now)

    def cleanup(self, retention_seconds: float = 86400 * 7) -> int:
        """Trigger background retention cleanup for expired records."""
        return self.expiration_manager.cleanup_expired(
            repository=self.repository,
            retention_seconds=retention_seconds,
        )

    def get_statistics(self, owner_id: Optional[str] = None) -> MemoryStatistics:
        """Generate storage and count statistics report."""
        return self.repository.get_statistics(owner_id=owner_id)
