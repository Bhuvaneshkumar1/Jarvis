"""
PIN Lockout State Models and Enums for JARVIS Security (Batch 13).
"""

from enum import Enum
import time
from typing import Optional
from pydantic import BaseModel, Field


class LockoutStatus(str, Enum):
    UNLOCKED = "UNLOCKED"
    ATTEMPT_TRACKING = "ATTEMPT_TRACKING"
    LOCKED = "LOCKED"
    RECOVERY_PENDING = "RECOVERY_PENDING"


class LockoutReason(str, Enum):
    MAXIMUM_FAILED_ATTEMPTS = "MAXIMUM_FAILED_ATTEMPTS"
    ADMINISTRATIVE_LOCK = "ADMINISTRATIVE_LOCK"
    SECURITY_RECOVERY_PENDING = "SECURITY_RECOVERY_PENDING"


class LockoutState(BaseModel):
    """
    Strongly Typed Persisted Lockout State Model.
    Guarantees no raw PINs, verifiers, or salts are present.
    """

    principal_id: str = Field(default="user")
    consecutive_failures: int = Field(default=0, ge=0)
    maximum_attempts: int = Field(default=3, ge=1)
    locked: bool = Field(default=False)
    locked_at: Optional[float] = Field(default=None)
    last_failure_at: Optional[float] = Field(default=None)
    last_success_at: Optional[float] = Field(default=None)
    lockout_reason: Optional[LockoutReason] = Field(default=None)
    state_version: int = Field(default=1, ge=1)
    updated_at: float = Field(default_factory=time.time)

    def get_status(self) -> LockoutStatus:
        if self.locked:
            return LockoutStatus.LOCKED
        if self.consecutive_failures > 0:
            return LockoutStatus.ATTEMPT_TRACKING
        return LockoutStatus.UNLOCKED
