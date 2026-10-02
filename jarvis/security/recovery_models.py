"""
Security Question Recovery Models and State Machine Enums for JARVIS Security (Batch 14).
"""

from enum import Enum
import time
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class RecoveryStateEnum(str, Enum):
    NORMAL = "NORMAL"
    PIN_LOCKED = "PIN_LOCKED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"
    RECOVERY_LOCKED = "RECOVERY_LOCKED"
    PIN_RESET_REQUIRED = "PIN_RESET_REQUIRED"


class SecurityQuestionCredential(BaseModel):
    """
    Persisted Security Question Credential Data Model.
    Never stores the recovery answer in plaintext.
    """

    principal_id: str = Field(default="user")
    question_id: str = Field(default="sq_primary")
    question_text: str = Field(..., min_length=5)
    salt: str = Field(..., min_length=16)
    answer_verifier: str = Field(..., min_length=16)
    algorithm: str = Field(default="pbkdf2_sha256")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class RecoveryChallenge(BaseModel):
    """
    Single-Use Recovery Challenge Token.
    """

    challenge_id: str = Field(..., min_length=16)
    principal_id: str = Field(default="user")
    question_text: str = Field(...)
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(...)
    consumed: bool = Field(default=False)
    consumed_at: Optional[float] = Field(default=None)

    def is_valid(self, now: Optional[float] = None) -> bool:
        current_time = now if now is not None else time.time()
        if self.consumed:
            return False
        if current_time >= self.expires_at:
            return False
        return True


class RecoveryLockoutState(BaseModel):
    """
    Persisted Recovery Lockout State Data Model for 1-Hour Security Lockout.
    """

    principal_id: str = Field(default="user")
    state: RecoveryStateEnum = Field(default=RecoveryStateEnum.NORMAL)
    recovery_locked: bool = Field(default=False)
    recovery_locked_at: Optional[float] = Field(default=None)
    recovery_lockout_expires_at: Optional[float] = Field(default=None)
    failed_recovery_attempts: int = Field(default=0, ge=0)
    state_version: int = Field(default=1, ge=1)
    updated_at: float = Field(default_factory=time.time)
