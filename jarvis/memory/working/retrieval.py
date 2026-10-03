"""
Selective Memory Retrieval Engine (Batch 25).
Combines repository queries, deterministic prioritization, security isolation, and token budgeting.
"""

import time
from typing import List, Optional
from jarvis.memory.working.models import WorkingMemoryEntry, MemoryRetrievalFilter
from jarvis.memory.working.repository import WorkingMemoryRepository
from jarvis.memory.working.prioritizer import MemoryPrioritizer
from jarvis.memory.working.token_budget import TokenBudgetManager


class SelectiveMemoryRetrievalEngine:
    """
    Selective Working Memory Retrieval Engine.
    Filters unauthorized context, prioritizes relevant entries, and enforces token budgets.
    """

    def __init__(
        self,
        prioritizer: Optional[MemoryPrioritizer] = None,
        budget_manager: Optional[TokenBudgetManager] = None,
    ):
        self.prioritizer = prioritizer or MemoryPrioritizer()
        self.budget_manager = budget_manager or TokenBudgetManager()

    def retrieve(
        self,
        repository: WorkingMemoryRepository,
        filter: MemoryRetrievalFilter,
        now: Optional[float] = None,
    ) -> List[WorkingMemoryEntry]:
        """
        Executes selective memory retrieval following security, priority, and budget rules.
        """
        current_time = now if now is not None else time.time()

        # Step 1: Query candidates from repository
        candidates = repository.list_memories(filter)
        if not candidates:
            return []

        # Step 2: Hard filter and rank memories deterministically
        ranked = self.prioritizer.rank_memories(candidates, filter, now=current_time)
        ranked_entries = [entry for entry, _ in ranked]

        # Step 3: Enforce token budget if specified
        if filter.token_budget and filter.token_budget > 0:
            selected, _, _ = self.budget_manager.fit_to_budget(
                entries=ranked_entries,
                max_tokens=filter.token_budget,
            )
            return selected[: filter.limit]

        return ranked_entries[: filter.limit]
