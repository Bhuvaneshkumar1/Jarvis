"""
Working Memory Prioritizer (Batch 25).
Provides deterministic ranking of memory entries based on explicit priority, scope relevance, recency, and keyword matching.
"""

import time
import math
from typing import List, Tuple, Optional
from jarvis.core.enums import SecurityLevel
from jarvis.memory.working.models import WorkingMemoryEntry, MemoryRetrievalFilter, MemoryStatus

# Security Level ordinal mapping for classification comparison
SECURITY_LEVEL_ORDER = {
    SecurityLevel.PUBLIC: 1,
    SecurityLevel.INTERNAL: 2,
    SecurityLevel.CONFIDENTIAL: 3,
    SecurityLevel.RESTRICTED: 4,
}


class MemoryPrioritizer:
    """
    Deterministic Memory Prioritizer.
    Enforces hard security/expiration filters before calculating scores.
    """

    def calculate_score(
        self,
        entry: WorkingMemoryEntry,
        filter: MemoryRetrievalFilter,
        now: Optional[float] = None,
    ) -> float:
        """
        Calculate ranking score for a memory entry.
        Returns float('-inf') if the entry is ineligible.
        """
        current_time = now if now is not None else time.time()

        # Hard Filter 1: Status must be ACTIVE
        if filter.active_only and entry.status != MemoryStatus.ACTIVE:
            return float("-inf")

        # Hard Filter 2: Expiration check
        if filter.exclude_expired and entry.expires_at is not None and entry.expires_at <= current_time:
            return float("-inf")

        # Hard Filter 3: Owner isolation check
        if entry.owner_id != filter.owner_id:
            return float("-inf")

        # Hard Filter 4: Classification privacy check
        entry_level = SECURITY_LEVEL_ORDER.get(entry.classification, 2)
        max_allowed = SECURITY_LEVEL_ORDER.get(filter.max_classification, 4)
        if entry_level > max_allowed:
            return float("-inf")

        # Hard Filter 5: Min priority constraint
        if entry.priority < filter.min_priority:
            return float("-inf")

        # --- Soft Preference Scoring ---
        # 1. Base score from explicit entry priority (range 1-10 -> 10 to 100)
        score = entry.priority * 10.0

        # 2. Scope match bonus
        if filter.scopes and entry.scope in filter.scopes:
            score += 25.0

        # 3. Specific identifier match bonuses
        if filter.task_id and entry.task_id == filter.task_id:
            score += 35.0
        if filter.conversation_id and entry.conversation_id == filter.conversation_id:
            score += 30.0
        if filter.agent_id and entry.agent_id == filter.agent_id:
            score += 30.0

        # 4. Recency bonus (decay 1 point per hour, max 20 points)
        age_hours = max(0.0, (current_time - entry.created_at) / 3600.0)
        recency_bonus = max(0.0, 20.0 - age_hours)
        score += recency_bonus

        # 5. Keyword match bonus if query is present
        if filter.query and filter.query.strip():
            keywords = [k.lower() for k in filter.query.strip().split() if len(k) > 2]
            content_lower = entry.content.lower()
            keyword_matches = sum(1 for kw in keywords if kw in content_lower)
            score += min(50.0, keyword_matches * 10.0)

        return score

    def rank_memories(
        self,
        entries: List[WorkingMemoryEntry],
        filter: MemoryRetrievalFilter,
        now: Optional[float] = None,
    ) -> List[Tuple[WorkingMemoryEntry, float]]:
        """
        Filters, scores, and deterministically ranks candidate memories.
        Returns list of (entry, score) tuples for eligible entries.
        """
        current_time = now if now is not None else time.time()
        scored_entries: List[Tuple[WorkingMemoryEntry, float]] = []

        for entry in entries:
            score = self.calculate_score(entry, filter, now=current_time)
            if not math.isinf(score) and score > float("-inf"):
                scored_entries.append((entry, score))

        # Deterministic Tie-Breaker:
        # Sort by: 1. score DESC, 2. priority DESC, 3. created_at DESC, 4. memory_id ASC
        scored_entries.sort(
            key=lambda x: (
                x[1],
                x[0].priority,
                x[0].created_at,
                -ord(x[0].memory_id[0]) if x[0].memory_id else 0,
            ),
            reverse=True,
        )

        return scored_entries
