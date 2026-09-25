from typing import List, Dict, Any, Optional


class MemoryRetrievalEngine:
    """
    Selective Memory Retrieval Engine interface.
    Manages local project knowledge, context indexing, and obsidian vault references.
    """

    def __init__(self, obsidian_vault_path: Optional[str] = None):
        self.obsidian_vault_path = obsidian_vault_path
        self._memory_store: List[Dict[str, Any]] = []

    def store_memory(self, key: str, content: str, tags: Optional[List[str]] = None):
        self._memory_store.append(
            {
                "key": key,
                "content": content,
                "tags": tags or [],
            }
        )

    def retrieve_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower()
        for item in self._memory_store:
            if q_lower in item["key"].lower() or q_lower in item["content"].lower():
                results.append(item)
            if len(results) >= limit:
                break
        return results
