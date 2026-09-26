"""
Typed Models & Value Representations for Secrets Management Subsystem (Batch 10).
"""

import enum
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


class SecretClassification(str, enum.Enum):
    """Classification levels for system parameters and credentials."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"
    CRITICAL_SECRET = "CRITICAL_SECRET"


class SecretSource(str, enum.Enum):
    """Origin source of loaded credentials."""

    ENVIRONMENT = "environment"
    ENCRYPTED_STORE = "encrypted_store"
    VAULT = "vault"


class SecretOperation(str, enum.Enum):
    """Permitted operations on secret store."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ROTATE = "rotate"


class SecretValue:
    """
    Secure container for sensitive secret data.
    Overrides __repr__, __str__, and __format__ to PREVENT accidental secret exposure in logs or tracebacks.
    Raw value is accessible ONLY via explicit get_unredacted_value() call by authorized components.
    """

    def __init__(self, raw_val: str):
        if not isinstance(raw_val, str):
            raise ValueError("SecretValue requires a string value.")
        self._raw_value: str = raw_val

    def __repr__(self) -> str:
        return "[REDACTED_SECRET_VALUE]"

    def __str__(self) -> str:
        return "[REDACTED_SECRET_VALUE]"

    def __format__(self, format_spec: str) -> str:
        return "[REDACTED_SECRET_VALUE]"

    def get_unredacted_value(self) -> str:
        """Returns the raw unredacted secret string for authorized caller use."""
        return self._raw_value

    def compute_fingerprint(self) -> str:
        """Computes SHA-256 fingerprint hash of secret value for non-leaking verification."""
        return hashlib.sha256(self._raw_value.encode("utf-8")).hexdigest()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SecretValue):
            return self._raw_value == other._raw_value
        return False


@dataclass(frozen=True)
class SecretMetadata:
    """Non-sensitive metadata snapshot for secret inspection and inventory."""

    identifier: str
    classification: SecretClassification
    source: SecretSource
    present: bool = True
    valid_format: bool = True
    fingerprint: str = ""
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Returns serializable metadata dictionary without secret values."""
        return {
            "identifier": self.identifier,
            "classification": self.classification.value,
            "source": self.source.value,
            "present": self.present,
            "valid_format": self.valid_format,
            "fingerprint": self.fingerprint,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SecretAccessRequest:
    """Access authorization request for a secret entry."""

    requester: str
    secret_identifier: str
    purpose: str = "operation"
    requested_operation: SecretOperation = SecretOperation.READ
    correlation_id: str = "system"


@dataclass(frozen=True)
class SecretAccessResult:
    """Result of secret access authorization evaluation."""

    allowed: bool
    secret_identifier: str
    secret_value: Optional[SecretValue] = None
    reason: str = "Authorized"
    audit_id: str = ""


@dataclass(frozen=True)
class SecretRotationRequest:
    """Request payload for secret rotation."""

    secret_identifier: str
    new_secret_value: SecretValue
    requester: str
    correlation_id: str = "system"


@dataclass(frozen=True)
class SecretRotationResult:
    """Result of secret rotation operation."""

    success: bool
    secret_identifier: str
    old_fingerprint: str = ""
    new_fingerprint: str = ""
    error: Optional[str] = None


@dataclass(frozen=True)
class SecretValidationResult:
    """Result of credential format/presence validation check."""

    valid: bool
    identifier: str
    reasons: List[str] = field(default_factory=list)
