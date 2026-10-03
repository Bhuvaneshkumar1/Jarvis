"""
Custom Exceptions for Working Memory Infrastructure (Batch 25).
Inherits from jarvis.core.exceptions.MemoryError.
"""

from jarvis.core.exceptions import MemoryError


class WorkingMemoryError(MemoryError):
    """Base exception for all working memory operations."""

    pass


class MemoryValidationError(WorkingMemoryError):
    """Raised when memory entry schema, scope, ownership, or payload fails validation."""

    pass


class MemoryNotFoundError(WorkingMemoryError):
    """Raised when a memory entry is not found or is soft-deleted/expired."""

    pass


class MemoryAccessDeniedError(WorkingMemoryError):
    """Raised when an unauthorized owner or agent attempts cross-scope access."""

    pass


class MemoryQuotaExceededError(WorkingMemoryError):
    """Raised when owner or scope storage content limits are exceeded."""

    pass


class MemoryBudgetExceededError(WorkingMemoryError):
    """Raised when token context budget constraints cannot fit required memories."""

    pass


class MemoryConcurrencyError(WorkingMemoryError):
    """Raised when optimistic concurrency version check fails during updates."""

    pass
