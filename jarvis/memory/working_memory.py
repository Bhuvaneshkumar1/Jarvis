"""
Facade Entry Point for Working Memory Subsystem (Batch 25).
Provides convenient functions and instance access for working memory management.
"""

from typing import Optional
from jarvis.database.manager import DatabaseManager
from jarvis.memory.working.manager import WorkingMemoryManager


_working_memory_manager_instance: Optional[WorkingMemoryManager] = None


def get_working_memory_manager(db_manager: Optional[DatabaseManager] = None) -> WorkingMemoryManager:
    """
    Obtain or initialize singleton WorkingMemoryManager instance.
    """
    global _working_memory_manager_instance
    if _working_memory_manager_instance is None or db_manager is not None:
        _working_memory_manager_instance = WorkingMemoryManager(db_manager=db_manager)
    return _working_memory_manager_instance


def reset_working_memory_manager() -> None:
    """Reset singleton instance (useful for unit testing)."""
    global _working_memory_manager_instance
    _working_memory_manager_instance = None
