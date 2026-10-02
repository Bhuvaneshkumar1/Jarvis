"""
Typed Exceptions for JARVIS Task Subsystem (Batch 17).
Re-exports authoritative task exceptions from core.exceptions to guarantee single class identity.
"""

from jarvis.core.exceptions import (
    JarvisError,
    TaskError,
    TaskNotFoundError,
    TaskInvalidStateTransitionError,
    InvalidTaskTransitionError,
    TaskVersionConflictError,
    TaskDependencyError,
    TaskDuplicateIdempotencyError,
    TaskAuthorizationError,
    TaskValidationError,
)

__all__ = [
    "JarvisError",
    "TaskError",
    "TaskNotFoundError",
    "TaskInvalidStateTransitionError",
    "InvalidTaskTransitionError",
    "TaskVersionConflictError",
    "TaskDependencyError",
    "TaskDuplicateIdempotencyError",
    "TaskAuthorizationError",
    "TaskValidationError",
]
