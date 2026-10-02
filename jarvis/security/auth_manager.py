"""
Authoritative Authentication Manager for JARVIS (Batch 12).
Unified orchestrator for PIN policy, secure hashing, persistence, sessions, audit, and events.
"""

import time
import uuid
from typing import Optional
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
from jarvis.security.events import (
    AuthenticationSucceededEvent,
    AuthenticationFailedEvent,
    SessionCreatedEvent,
    SessionRevokedEvent,
    PinChangedEvent,
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus
from jarvis.core.exceptions import (
    PinPolicyValidationError,
    CredentialCorruptedError,
    SessionExpiredError,
    SessionRevokedError,
)


class AuthenticationManager:
    """
    Centralized Authentication Subsystem for JARVIS.
    Enforces PIN enrollment, constant-time verification, session management,
    audit trail generation, and typed security event publishing.
    """

    def __init__(
        self,
        policy: Optional[PinPolicy] = None,
        hasher: Optional[PINHasher] = None,
        credential_store: Optional[PinCredentialStore] = None,
        session_manager: Optional[SessionManager] = None,
        attempt_tracker: Optional[AttemptTracker] = None,
        audit_logger: Optional[AuditLogger] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.policy = policy or PinPolicy()
        self.hasher = hasher or PINHasher()
        self.credential_store = credential_store or PinCredentialStore()
        self.session_manager = session_manager or SessionManager()
        self.attempt_tracker = attempt_tracker or AttemptTracker()
        self.audit_logger = audit_logger or AuditLogger()
        self.event_bus = event_bus

    def is_enrolled(self, principal: str = "user") -> bool:
        """
        Returns True if a PIN credential is currently enrolled for principal.
        """
        return self.credential_store.has_credential(principal)

    def enroll_pin(self, pin: str, confirm_pin: str, principal: str = "user") -> AuthenticationResult:
        """
        Enrolls a new PIN credential.
        Fails if already enrolled, policy check fails, or confirmation mismatches.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        if self.is_enrolled(principal):
            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_ENROLLMENT_FAILURE",
                result="REJECTED",
                correlation_id=correlation_id,
                error="PIN credential already enrolled.",
                details={"principal": principal, "reason": "ALREADY_ENROLLED"},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="ALREADY_ENROLLED",
                metadata={"reason": "Credential already enrolled. Use PIN change or explicit reset."},
            )

        try:
            self.policy.validate_pin_confirmation(pin, confirm_pin)
        except PinPolicyValidationError as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_ENROLLMENT_FAILURE",
                result="INVALID_POLICY",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="POLICY_VALIDATION_FAILED",
                metadata={"error": str(e)},
            )

        try:
            salt_hex, verifier_hex, params = self.hasher.derive_verifier(pin)
            cred = PinCredential(
                credential_id=f"pin_{principal}",
                principal=principal,
                algorithm=params.get("algorithm", "pbkdf2_sha256"),
                salt=salt_hex,
                verifier=verifier_hex,
                parameters=params,
                created_at=timestamp,
                updated_at=timestamp,
                enabled=True,
            )

            # Persist and post-verify
            self.credential_store.save_credential(cred)

            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_ENROLLMENT_SUCCESS",
                result="SUCCESS",
                correlation_id=correlation_id,
                details={"principal": principal, "algorithm": cred.algorithm},
            )

            return AuthenticationResult(
                status=AuthenticationStatus.SUCCESS,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                metadata={"principal": principal, "message": "PIN enrolled successfully."},
            )
        except Exception as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_ENROLLMENT_FAILURE",
                result="ERROR",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.AUTHENTICATION_UNAVAILABLE,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="STORAGE_ERROR",
                metadata={"error": "Enrollment failed due to storage error."},
            )

    def verify_pin(self, pin: str, principal: str = "user") -> AuthenticationResult:
        """
        Verifies PIN candidate against stored credential and creates authenticated session on success.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        try:
            cred = self.credential_store.load_credential(principal)
        except CredentialCorruptedError as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="CREDENTIAL_CORRUPTED",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.CREDENTIAL_CORRUPTED,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="CREDENTIAL_CORRUPTED",
            )

        if cred is None or not cred.enabled:
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="NOT_ENROLLED",
                correlation_id=correlation_id,
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.NOT_ENROLLED,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="NOT_ENROLLED",
            )

        # Basic input structure check
        if pin is None or not isinstance(pin, str) or len(pin) == 0:
            self.attempt_tracker.record_failure(principal)
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="INVALID_INPUT",
                correlation_id=correlation_id,
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="MALFORMED_INPUT",
            )

        try:
            is_valid = self.hasher.verify_pin(
                candidate_pin=pin,
                salt_hex=cred.salt,
                stored_verifier_hex=cred.verifier,
                parameters=cred.parameters,
            )
        except CredentialCorruptedError as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="CREDENTIAL_CORRUPTED",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.CREDENTIAL_CORRUPTED,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="CREDENTIAL_CORRUPTED",
            )
        except Exception as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="ERROR",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.AUTHENTICATION_UNAVAILABLE,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="AUTH_SYSTEM_ERROR",
            )

        if not is_valid:
            attempts = self.attempt_tracker.record_failure(principal)
            self.audit_logger.log_event(
                component="auth_manager",
                action="AUTHENTICATION_FAILURE",
                result="INVALID_PIN",
                correlation_id=correlation_id,
                details={"principal": principal, "failed_attempts_count": attempts},
            )

            if self.event_bus:
                try:
                    self.event_bus.publish_sync(
                        AuthenticationFailedEvent(
                            correlation_id=correlation_id,
                            payload={"principal": principal, "reason": "INVALID_PIN"},
                        )
                    )
                except Exception:
                    pass

            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_PIN,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="INVALID_PIN",
            )

        # Verification Succeeded
        self.attempt_tracker.record_success(principal)
        session = self.session_manager.create_session(principal)

        self.audit_logger.log_event(
            component="auth_manager",
            action="AUTHENTICATION_SUCCESS",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal": principal, "session_id": session.session_id},
        )
        self.audit_logger.log_event(
            component="auth_manager",
            action="SESSION_CREATED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"session_id": session.session_id, "expires_at": session.expires_at},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    AuthenticationSucceededEvent(
                        correlation_id=correlation_id,
                        session_id=session.session_id,
                        payload={"principal": principal},
                    )
                )
                self.event_bus.publish_sync(
                    SessionCreatedEvent(
                        correlation_id=correlation_id,
                        session_id=session.session_id,
                        payload={"principal": principal, "expires_at": session.expires_at},
                    )
                )
            except Exception:
                pass

        return AuthenticationResult(
            status=AuthenticationStatus.SUCCESS,
            authenticated=True,
            session_id=session.session_id,
            timestamp=timestamp,
            correlation_id=correlation_id,
            metadata={"principal": principal},
        )

    def change_pin(
        self,
        current_pin: str,
        new_pin: str,
        confirm_new_pin: str,
        session_id: Optional[str] = None,
        principal: str = "user",
    ) -> AuthenticationResult:
        """
        Changes stored PIN credential after verifying current PIN and new PIN policy.
        Revokes existing active sessions upon successful change.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        if session_id:
            try:
                valid_sess = self.session_manager.validate_session(session_id)
                if not valid_sess:
                    return AuthenticationResult(
                        status=AuthenticationStatus.INVALID_INPUT,
                        authenticated=False,
                        timestamp=timestamp,
                        correlation_id=correlation_id,
                        safe_error_code="SESSION_EXPIRED",
                    )
            except (SessionExpiredError, SessionRevokedError) as e:
                return AuthenticationResult(
                    status=AuthenticationStatus.INVALID_INPUT,
                    authenticated=False,
                    timestamp=timestamp,
                    correlation_id=correlation_id,
                    safe_error_code="INVALID_SESSION",
                    metadata={"error": str(e)},
                )

        if not self.is_enrolled(principal):
            return AuthenticationResult(
                status=AuthenticationStatus.NOT_ENROLLED,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="NOT_ENROLLED",
            )

        # Verify current PIN
        try:
            cred = self.credential_store.load_credential(principal)
            if cred is None or not self.hasher.verify_pin(current_pin, cred.salt, cred.verifier, cred.parameters):
                self.audit_logger.log_event(
                    component="auth_manager",
                    action="PIN_CHANGE_FAILURE",
                    result="INVALID_CURRENT_PIN",
                    correlation_id=correlation_id,
                    details={"principal": principal},
                )
                return AuthenticationResult(
                    status=AuthenticationStatus.INVALID_PIN,
                    authenticated=False,
                    timestamp=timestamp,
                    correlation_id=correlation_id,
                    safe_error_code="INVALID_CURRENT_PIN",
                )
        except Exception as e:
            return AuthenticationResult(
                status=AuthenticationStatus.AUTHENTICATION_UNAVAILABLE,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="VERIFICATION_FAILED",
                metadata={"error": str(e)},
            )

        # Validate new PIN policy & confirmation
        try:
            self.policy.validate_pin_confirmation(new_pin, confirm_new_pin)
        except PinPolicyValidationError as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_CHANGE_FAILURE",
                result="INVALID_NEW_PIN_POLICY",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="POLICY_VALIDATION_FAILED",
                metadata={"error": str(e)},
            )

        # Reject same PIN as current if desired
        if current_pin == new_pin:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="SAME_PIN_PROHIBITED",
                metadata={"error": "New PIN cannot be identical to current PIN."},
            )

        # Update credential atomically
        try:
            salt_hex, verifier_hex, params = self.hasher.derive_verifier(new_pin)
            updated_cred = PinCredential(
                credential_id=f"pin_{principal}",
                principal=principal,
                algorithm=params.get("algorithm", "pbkdf2_sha256"),
                salt=salt_hex,
                verifier=verifier_hex,
                parameters=params,
                created_at=cred.created_at,
                updated_at=timestamp,
                credential_version=cred.credential_version + 1,
                enabled=True,
            )
            self.credential_store.save_credential(updated_cred)

            # Revoke all sessions on PIN change
            revoked_count = self.session_manager.revoke_all_sessions()

            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_CHANGE_SUCCESS",
                result="SUCCESS",
                correlation_id=correlation_id,
                details={"principal": principal, "revoked_sessions_count": revoked_count},
            )

            if self.event_bus:
                try:
                    self.event_bus.publish_sync(
                        PinChangedEvent(
                            correlation_id=correlation_id,
                            payload={"principal": principal, "revoked_sessions": revoked_count},
                        )
                    )
                except Exception:
                    pass

            return AuthenticationResult(
                status=AuthenticationStatus.SUCCESS,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                metadata={"message": "PIN changed successfully. Sessions revoked."},
            )
        except Exception as e:
            self.audit_logger.log_event(
                component="auth_manager",
                action="PIN_CHANGE_FAILURE",
                result="ERROR",
                correlation_id=correlation_id,
                error=str(e),
                details={"principal": principal},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.AUTHENTICATION_UNAVAILABLE,
                authenticated=False,
                timestamp=timestamp,
                correlation_id=correlation_id,
                safe_error_code="UPDATE_FAILED",
            )

        def validate_session(self, session_id: str) -> Optional[AuthSession]:
            return self.session_manager.validate_session(session_id)

    def validate_session(self, session_id: str) -> Optional[AuthSession]:
        try:
            return self.session_manager.validate_session(session_id)
        except (SessionExpiredError, SessionRevokedError):
            self.audit_logger.log_event(
                component="auth_manager",
                action="SESSION_VALIDATION_FAILURE",
                result="INVALID_SESSION",
                details={"session_id": session_id},
            )
            raise

    def revoke_session(self, session_id: str) -> bool:
        res = self.session_manager.revoke_session(session_id)
        if res:
            self.audit_logger.log_event(
                component="auth_manager",
                action="SESSION_REVOKED",
                result="SUCCESS",
                details={"session_id": session_id},
            )
            if self.event_bus:
                try:
                    self.event_bus.publish_sync(SessionRevokedEvent(session_id=session_id))
                except Exception:
                    pass
        return res

    def revoke_all_sessions(self) -> int:
        return self.session_manager.revoke_all_sessions()

    def get_authentication_context(self, session_id: str) -> AuthenticationContext:
        return self.session_manager.get_authentication_context(session_id)
