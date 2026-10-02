"""
JARVIS Centralized Persistent State Recovery Subsystem (Batch 19).
"""

from jarvis.core.recovery.models import (
    RecoveryStatus,
    OperationClassification,
    RecoveryRecord,
    OutboxEventRecord,
)
from jarvis.core.recovery.store import RecoveryRepository
from jarvis.core.recovery.handlers import (
    TaskRecoveryHandler,
    ApprovalRecoveryHandler,
    EventOutboxHandler,
)
from jarvis.core.recovery.coordinator import RecoveryCoordinator
from jarvis.core.exceptions import (
    RecoveryError,
    RecoveryLockError,
    RecoveryIntegrityError,
    RecoveryAuthorizationError,
)

__all__ = [
    "RecoveryStatus",
    "OperationClassification",
    "RecoveryRecord",
    "OutboxEventRecord",
    "RecoveryRepository",
    "TaskRecoveryHandler",
    "ApprovalRecoveryHandler",
    "EventOutboxHandler",
    "RecoveryCoordinator",
    "RecoveryError",
    "RecoveryLockError",
    "RecoveryIntegrityError",
    "RecoveryAuthorizationError",
]
