"""
Typed Authentication Event Contracts for JARVIS Event Bus (Batch 12).
All event payloads contain safe metadata only; raw PINs and credentials are strictly excluded.
"""

from jarvis.core.events.contracts import Event


class AuthenticationSucceededEvent(Event):
    event_type: str = "AuthenticationSucceeded"


class AuthenticationFailedEvent(Event):
    event_type: str = "AuthenticationFailed"


class SessionCreatedEvent(Event):
    event_type: str = "SessionCreated"


class SessionRevokedEvent(Event):
    event_type: str = "SessionRevoked"


class PinChangedEvent(Event):
    event_type: str = "PinChanged"


class PinAttemptFailedEvent(Event):
    event_type: str = "PinAttemptFailed"


class PinAttemptSucceededEvent(Event):
    event_type: str = "PinAttemptSucceeded"


class PinLockoutTriggeredEvent(Event):
    event_type: str = "PinLockoutTriggered"


class PinAuthenticationBlockedEvent(Event):
    event_type: str = "PinAuthenticationBlocked"


class SessionRevokedDueToLockoutEvent(Event):
    event_type: str = "SessionRevokedDueToLockout"


class SecurityQuestionEnrolledEvent(Event):
    event_type: str = "SecurityQuestionEnrolled"


class SecurityQuestionUpdatedEvent(Event):
    event_type: str = "SecurityQuestionUpdated"


class SecurityRecoveryStartedEvent(Event):
    event_type: str = "SecurityRecoveryStarted"


class SecurityRecoveryAnswerFailedEvent(Event):
    event_type: str = "SecurityRecoveryAnswerFailed"


class SecurityRecoveryAnswerVerifiedEvent(Event):
    event_type: str = "SecurityRecoveryAnswerVerified"


class SecurityRecoveryLockoutStartedEvent(Event):
    event_type: str = "SecurityRecoveryLockoutStarted"


class SecurityPinResetCompletedEvent(Event):
    event_type: str = "SecurityPinResetCompleted"


class SecurityRecoveryDeniedEvent(Event):
    event_type: str = "SecurityRecoveryDenied"
