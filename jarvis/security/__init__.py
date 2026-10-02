"""
JARVIS Security Subsystem (Batch 12 & Batch 13).
Authoritative entry point for PIN policy, secure storage, verification, sessions, attempt tracking, and 3-attempt lockout.
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
from jarvis.security.lockout_models import LockoutStatus, LockoutReason, LockoutState
from jarvis.security.lockout_store import LockoutStore
from jarvis.security.lockout_manager import LockoutManager, LockoutRecoveryService
from jarvis.security.auth_manager import AuthenticationManager
from jarvis.security.events import (
    AuthenticationSucceededEvent,
    AuthenticationFailedEvent,
    SessionCreatedEvent,
    SessionRevokedEvent,
    PinChangedEvent,
    PinAttemptFailedEvent,
    PinAttemptSucceededEvent,
    PinLockoutTriggeredEvent,
    PinAuthenticationBlockedEvent,
    SessionRevokedDueToLockoutEvent,
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
    "LockoutStatus",
    "LockoutReason",
    "LockoutState",
    "LockoutStore",
    "LockoutManager",
    "LockoutRecoveryService",
    "AuthenticationManager",
    "AuthenticationSucceededEvent",
    "AuthenticationFailedEvent",
    "SessionCreatedEvent",
    "SessionRevokedEvent",
    "PinChangedEvent",
    "PinAttemptFailedEvent",
    "PinAttemptSucceededEvent",
    "PinLockoutTriggeredEvent",
    "PinAuthenticationBlockedEvent",
    "SessionRevokedDueToLockoutEvent",
]
