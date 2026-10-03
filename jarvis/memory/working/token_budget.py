"""
Token Budget Manager for Working Memory (Batch 25).
Estimates token overhead and fits prioritized memories into provider context windows without silent truncation.
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from jarvis.memory.working.models import WorkingMemoryEntry


class TokenBudgetManager:
    """
    Manages context token allocations for retrieved working memory.
    """

    def estimate_tokens(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Estimate token usage for text content and metadata overhead.
        Uses conservative heuristic of 3.5 characters per token.
        """
        if not text:
            return 0
        char_count = len(text)
        tokens = math.ceil(char_count / 3.5)

        # Add overhead for metadata fields if present
        if metadata:
            meta_str = str(metadata)
            tokens += math.ceil(len(meta_str) / 4.0)

        # Base entry framing overhead (role/timestamp/source tags)
        tokens += 15
        return tokens

    def fit_to_budget(
        self,
        entries: List[WorkingMemoryEntry],
        max_tokens: int,
        reserved_tokens: int = 0,
    ) -> Tuple[List[WorkingMemoryEntry], List[WorkingMemoryEntry], int]:
        """
        Selects prioritized entries that fit within max_tokens budget.

        Returns:
            (selected_entries, omitted_entries, total_used_tokens)
        """
        available_budget = max_tokens - reserved_tokens
        if available_budget <= 0:
            return [], entries, 0

        selected: List[WorkingMemoryEntry] = []
        omitted: List[WorkingMemoryEntry] = []
        total_tokens = 0

        for entry in entries:
            entry_tokens = self.estimate_tokens(entry.content, entry.metadata)
            if total_tokens + entry_tokens <= available_budget:
                selected.append(entry)
                total_tokens += entry_tokens
            else:
                omitted.append(entry)

        return selected, omitted, total_tokens
