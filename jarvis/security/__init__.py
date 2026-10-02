"""
JARVIS Security & PIN Authentication Subsystem (Batch 12).
Authoritative entry point for PIN policy, secure storage, authentication verification, and sessions.
"""

from jarvis.security.contracts import (
    AuthenticationStatus,
    AuthenticationResult,
    AuthenticationContext,
    PinCredential,
    AuthSession,
)
from jarvis.security.pin_policy import PinPolicy
from jarvis.security.pin_crypto import PINHasher
from jarvis.security.credential_store import PinCredentialStore
from jarvis.security.session_manager import SessionManager
from jarvis.security.rate_limit import AttemptTracker
from jarvis.security.auth_manager import AuthenticationManager
from jarvis.security.events import (
    AuthenticationSucceededEvent,
    AuthenticationFailedEvent,
    SessionCreatedEvent,
    SessionRevokedEvent,
    PinChangedEvent,
)

__all__ = [
    "AuthenticationStatus",
    "AuthenticationResult",
    "AuthenticationContext",
    "PinCredential",
    "AuthSession",
    "PinPolicy",
    "PINHasher",
    "PinCredentialStore",
    "SessionManager",
    "AttemptTracker",
    "AuthenticationManager",
    "AuthenticationSucceededEvent",
    "AuthenticationFailedEvent",
    "SessionCreatedEvent",
    "SessionRevokedEvent",
    "PinChangedEvent",
]
