"""
Authentication Contracts, Models, and Enums for JARVIS Security (Batch 12).
"""

from enum import Enum
import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class AuthenticationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INVALID_PIN = "INVALID_PIN"
    NOT_ENROLLED = "NOT_ENROLLED"
    INVALID_INPUT = "INVALID_INPUT"
    CREDENTIAL_CORRUPTED = "CREDENTIAL_CORRUPTED"
    AUTHENTICATION_UNAVAILABLE = "AUTHENTICATION_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AuthenticationResult(BaseModel):
    """
    Structured Authentication Result Contract.
    Guarantees no raw PINs, salts, or verifiers are exposed.
    """

    status: AuthenticationStatus
    authenticated: bool
    session_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    correlation_id: str = Field(default="")
    safe_error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def sanitize_result_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        forbidden_keys = {"pin", "confirm_pin", "new_pin", "current_pin", "salt", "verifier", "raw_pin"}
        sanitized = {}
        for key, val in v.items():
            if key.lower() in forbidden_keys:
                continue
            sanitized[key] = val
        return sanitized


class AuthenticationContext(BaseModel):
    """
    Trusted Authentication Principal Context passed to Policy Engine / Authorization.
    """

    principal: str = Field(default="user")
    session_id: str
    authentication_method: str = Field(default="PIN")
    authenticated_at: float = Field(default_factory=time.time)
    expires_at: float
    assurance_level: str = Field(default="PIN_HIGH")


class PinCredential(BaseModel):
    """
    Persisted PIN Credential Data Model. Never contains raw PIN.
    """

    credential_id: str = Field(default="pin_primary")
    principal: str = Field(default="user")
    algorithm: str = Field(default="pbkdf2_sha256")
    salt: str = Field(..., min_length=16)
    verifier: str = Field(..., min_length=16)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    credential_version: int = Field(default=1, ge=1)
    enabled: bool = Field(default=True)


class AuthSession(BaseModel):
    """
    Authenticated Session Contract.
    """

    session_id: str = Field(..., min_length=16)
    principal: str = Field(default="user")
    created_at: float = Field(default_factory=time.time)
    last_activity_at: float = Field(default_factory=time.time)
    expires_at: float
    inactivity_timeout: float = Field(default=900.0)  # 15 minutes
    authentication_method: str = Field(default="PIN")
    authentication_state: str = Field(default="AUTHENTICATED")
    revoked_at: Optional[float] = None

    def is_active(self, now: Optional[float] = None) -> bool:
        current_time = now if now is not None else time.time()
        if self.revoked_at is not None:
            return False
        if current_time >= self.expires_at:
            return False
        if current_time - self.last_activity_at > self.inactivity_timeout:
            return False
        return True

    def is_expired(self, now: Optional[float] = None) -> bool:
        current_time = now if now is not None else time.time()
        if current_time >= self.expires_at:
            return True
        if current_time - self.last_activity_at > self.inactivity_timeout:
            return True
        return False

    def is_revoked(self) -> bool:
        return self.revoked_at is not None
