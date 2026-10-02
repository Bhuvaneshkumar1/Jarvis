"""
Security Question Recovery Service & 1-Hour Lockout Engine for JARVIS (Batch 14).
"""

import time
import uuid
import secrets
from typing import Optional, Tuple, Dict, Callable
from jarvis.security.contracts import (
    AuthenticationStatus,
    AuthenticationResult,
    PinCredential,
)
from jarvis.security.recovery_models import (
    RecoveryStateEnum,
    SecurityQuestionCredential,
    RecoveryChallenge,
)
from jarvis.security.recovery_crypto import RecoveryAnswerHasher
from jarvis.security.recovery_store import RecoveryStore
from jarvis.security.pin_crypto import PINHasher
from jarvis.security.pin_policy import PinPolicy
from jarvis.security.credential_store import PinCredentialStore
from jarvis.security.session_manager import SessionManager
from jarvis.security.lockout_manager import LockoutManager
from jarvis.security.events import (
    SecurityQuestionEnrolledEvent,
    SecurityQuestionUpdatedEvent,
    SecurityRecoveryStartedEvent,
    SecurityRecoveryAnswerFailedEvent,
    SecurityRecoveryAnswerVerifiedEvent,
    SecurityRecoveryLockoutStartedEvent,
    SecurityPinResetCompletedEvent,
    SecurityRecoveryDeniedEvent,
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus
from jarvis.core.exceptions import (
    PinPolicyValidationError,
)

ONE_HOUR_SECONDS = 3600.0
CHALLENGE_TTL_SECONDS = 600.0  # 10 minutes


class RecoveryService:
    """
    Security Question Recovery Subsystem handling enrollment, challenges, answer verification,
    PIN replacement, and 60-minute security lockout.
    """

    def __init__(
        self,
        recovery_store: Optional[RecoveryStore] = None,
        answer_hasher: Optional[RecoveryAnswerHasher] = None,
        pin_hasher: Optional[PINHasher] = None,
        pin_policy: Optional[PinPolicy] = None,
        credential_store: Optional[PinCredentialStore] = None,
        session_manager: Optional[SessionManager] = None,
        lockout_manager: Optional[LockoutManager] = None,
        audit_logger: Optional[AuditLogger] = None,
        event_bus: Optional[EventBus] = None,
        clock_fn: Optional[Callable[[], float]] = None,
    ):
        self.recovery_store = recovery_store or RecoveryStore()
        self.answer_hasher = answer_hasher or RecoveryAnswerHasher()
        self.pin_hasher = pin_hasher or PINHasher()
        self.pin_policy = pin_policy or PinPolicy()
        self.credential_store = credential_store or PinCredentialStore()
        self.session_manager = session_manager or SessionManager()
        self.lockout_manager = lockout_manager or LockoutManager()
        self.audit_logger = audit_logger or AuditLogger()
        self.event_bus = event_bus
        self.clock_fn = clock_fn or time.time
        self._challenges: Dict[str, RecoveryChallenge] = {}

    def _now(self) -> float:
        return self.clock_fn()

    def check_recovery_lockout(self, principal_id: str = "user") -> Tuple[bool, Optional[float]]:
        """
        Checks if 60-minute recovery lockout is currently active for principal.
        Returns Tuple[is_locked, lockout_expires_at].
        """
        now = self._now()
        state = self.recovery_store.load_recovery_state(principal_id)

        if state.recovery_locked:
            if state.recovery_lockout_expires_at and now < state.recovery_lockout_expires_at:
                return True, state.recovery_lockout_expires_at
            else:
                # Lockout expired: clear recovery lock state
                updated_state = state.model_copy(
                    update={
                        "recovery_locked": False,
                        "recovery_locked_at": None,
                        "recovery_lockout_expires_at": None,
                        "state": RecoveryStateEnum.PIN_LOCKED,
                        "state_version": state.state_version + 1,
                        "updated_at": now,
                    }
                )
                self.recovery_store.save_recovery_state(updated_state)

                self.audit_logger.log_event(
                    component="recovery_service",
                    action="SECURITY_RECOVERY_LOCKOUT_EXPIRED",
                    result="SUCCESS",
                    details={"principal_id": principal_id},
                )
                return False, None

        return False, None

    # =========================================================================
    # ENROLLMENT & UPDATE
    # =========================================================================

    def enroll_security_question(self, current_pin: str, question_text: str, answer: str, principal_id: str = "user") -> AuthenticationResult:
        """
        Enrolls a security question and answer after verifying the owner's PIN.
        Fails if already enrolled or PIN verification fails.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        now = self._now()

        if self.recovery_store.has_question_credential(principal_id):
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="ALREADY_ENROLLED",
                metadata={"error": "Security question already enrolled. Use update_security_question instead."},
            )

        # Reauthenticate PIN
        cred = self.credential_store.load_credential(principal_id)
        if cred is None or not self.pin_hasher.verify_pin(current_pin, cred.salt, cred.verifier, cred.parameters):
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_DENIED",
                result="INVALID_PIN",
                correlation_id=correlation_id,
                details={"principal_id": principal_id, "action": "ENROLL"},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_PIN,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_PIN",
            )

        # Validate question text and answer
        if not question_text or not isinstance(question_text, str) or len(question_text.strip()) < 5:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_QUESTION_TEXT",
            )

        try:
            salt_hex, verifier_hex, params = self.answer_hasher.derive_answer_verifier(answer)
        except ValueError as e:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_ANSWER",
                metadata={"error": str(e)},
            )

        sq_cred = SecurityQuestionCredential(
            principal_id=principal_id,
            question_id=f"sq_{principal_id}",
            question_text=question_text.strip(),
            salt=salt_hex,
            answer_verifier=verifier_hex,
            algorithm=params.get("algorithm", "pbkdf2_sha256"),
            parameters=params,
            created_at=now,
            updated_at=now,
        )

        self.recovery_store.save_question_credential(sq_cred)

        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_QUESTION_ENROLLED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    SecurityQuestionEnrolledEvent(
                        correlation_id=correlation_id,
                        payload={"principal_id": principal_id},
                    )
                )
            except Exception:
                pass

        return AuthenticationResult(
            status=AuthenticationStatus.SUCCESS,
            authenticated=False,
            timestamp=now,
            correlation_id=correlation_id,
            metadata={"message": "Security question enrolled successfully."},
        )

    def update_security_question(self, current_pin: str, new_question_text: str, new_answer: str, principal_id: str = "user") -> AuthenticationResult:
        """
        Updates an existing security question and answer after verifying PIN.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        now = self._now()

        cred = self.credential_store.load_credential(principal_id)
        if cred is None or not self.pin_hasher.verify_pin(current_pin, cred.salt, cred.verifier, cred.parameters):
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_DENIED",
                result="INVALID_PIN",
                correlation_id=correlation_id,
                details={"principal_id": principal_id, "action": "UPDATE"},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_PIN,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_PIN",
            )

        if not new_question_text or not isinstance(new_question_text, str) or len(new_question_text.strip()) < 5:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_QUESTION_TEXT",
            )

        try:
            salt_hex, verifier_hex, params = self.answer_hasher.derive_answer_verifier(new_answer)
        except ValueError as e:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_ANSWER",
                metadata={"error": str(e)},
            )

        existing = self.recovery_store.load_question_credential(principal_id)
        created_at = existing.created_at if existing else now

        sq_cred = SecurityQuestionCredential(
            principal_id=principal_id,
            question_id=f"sq_{principal_id}",
            question_text=new_question_text.strip(),
            salt=salt_hex,
            answer_verifier=verifier_hex,
            algorithm=params.get("algorithm", "pbkdf2_sha256"),
            parameters=params,
            created_at=created_at,
            updated_at=now,
        )

        self.recovery_store.save_question_credential(sq_cred)

        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_QUESTION_UPDATED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    SecurityQuestionUpdatedEvent(
                        correlation_id=correlation_id,
                        payload={"principal_id": principal_id},
                    )
                )
            except Exception:
                pass

        return AuthenticationResult(
            status=AuthenticationStatus.SUCCESS,
            authenticated=False,
            timestamp=now,
            correlation_id=correlation_id,
            metadata={"message": "Security question updated successfully."},
        )

    # =========================================================================
    # RECOVERY WORKFLOW
    # =========================================================================

    def initiate_recovery(self, principal_id: str = "user") -> Tuple[AuthenticationResult, Optional[RecoveryChallenge]]:
        """
        Initiates recovery flow when account is PIN locked.
        Presents question & returns single-use RecoveryChallenge.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        now = self._now()

        # Check 60-minute recovery lockout
        is_rec_locked, expires_at = self.check_recovery_lockout(principal_id)
        if is_rec_locked:
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_DENIED",
                result="RECOVERY_LOCKED",
                correlation_id=correlation_id,
                details={"principal_id": principal_id, "expires_at": expires_at},
            )
            if self.event_bus:
                try:
                    self.event_bus.publish_sync(
                        SecurityRecoveryDeniedEvent(
                            correlation_id=correlation_id,
                            payload={"principal_id": principal_id, "reason": "RECOVERY_LOCKED", "expires_at": expires_at},
                        )
                    )
                except Exception:
                    pass

            return (
                AuthenticationResult(
                    status=AuthenticationStatus.ACCOUNT_LOCKED,
                    authenticated=False,
                    timestamp=now,
                    correlation_id=correlation_id,
                    safe_error_code="RECOVERY_LOCKED",
                    metadata={"locked": True, "recovery_lockout_expires_at": expires_at},
                ),
                None,
            )

        # Fail closed if question is not enrolled
        sq_cred = self.recovery_store.load_question_credential(principal_id)
        if sq_cred is None:
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_DENIED",
                result="NOT_ENROLLED",
                correlation_id=correlation_id,
                details={"principal_id": principal_id},
            )
            return (
                AuthenticationResult(
                    status=AuthenticationStatus.NOT_ENROLLED,
                    authenticated=False,
                    timestamp=now,
                    correlation_id=correlation_id,
                    safe_error_code="QUESTION_NOT_ENROLLED",
                    metadata={"error": "No security question enrolled for this account."},
                ),
                None,
            )

        challenge_id = f"chal_{secrets.token_urlsafe(32)}"
        challenge = RecoveryChallenge(
            challenge_id=challenge_id,
            principal_id=principal_id,
            question_text=sq_cred.question_text,
            created_at=now,
            expires_at=now + CHALLENGE_TTL_SECONDS,
            consumed=False,
        )

        self._challenges[challenge_id] = challenge

        state = self.recovery_store.load_recovery_state(principal_id)
        updated_state = state.model_copy(
            update={
                "state": RecoveryStateEnum.RECOVERY_PENDING,
                "state_version": state.state_version + 1,
                "updated_at": now,
            }
        )
        self.recovery_store.save_recovery_state(updated_state)

        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_RECOVERY_STARTED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id, "challenge_id": challenge_id},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    SecurityRecoveryStartedEvent(
                        correlation_id=correlation_id,
                        payload={"principal_id": principal_id, "challenge_id": challenge_id},
                    )
                )
            except Exception:
                pass

        return (
            AuthenticationResult(
                status=AuthenticationStatus.SUCCESS,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                metadata={
                    "challenge_id": challenge_id,
                    "question_text": sq_cred.question_text,
                    "expires_at": challenge.expires_at,
                },
            ),
            challenge,
        )

    def submit_recovery_answer(self, challenge_id: str, answer: str, principal_id: str = "user") -> AuthenticationResult:
        """
        Submits recovery answer for challenge token.
        If correct: transitions state to PIN_RESET_REQUIRED.
        If incorrect: triggers 60-MINUTE SECURITY LOCKOUT (RECOVERY_LOCKED) & revokes all sessions.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        now = self._now()

        # Check 60-minute recovery lockout
        is_rec_locked, expires_at = self.check_recovery_lockout(principal_id)
        if is_rec_locked:
            return AuthenticationResult(
                status=AuthenticationStatus.ACCOUNT_LOCKED,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="RECOVERY_LOCKED",
                metadata={"locked": True, "recovery_lockout_expires_at": expires_at},
            )

        # Validate challenge
        challenge = self._challenges.get(challenge_id)
        if challenge is None or not challenge.is_valid(now=now) or challenge.principal_id != principal_id:
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_CHALLENGE_REJECTED",
                result="INVALID_CHALLENGE",
                correlation_id=correlation_id,
                details={"challenge_id": challenge_id, "principal_id": principal_id},
            )
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_CHALLENGE",
                metadata={"error": "Challenge is invalid, expired, or already consumed."},
            )

        # Consume challenge atomically
        consumed_challenge = challenge.model_copy(update={"consumed": True, "consumed_at": now})
        self._challenges[challenge_id] = consumed_challenge

        # Load question credential
        sq_cred = self.recovery_store.load_question_credential(principal_id)
        if sq_cred is None:
            return AuthenticationResult(
                status=AuthenticationStatus.NOT_ENROLLED,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="QUESTION_NOT_ENROLLED",
            )

        # Verify Answer
        try:
            is_correct = self.answer_hasher.verify_answer(
                candidate_answer=answer,
                salt_hex=sq_cred.salt,
                stored_verifier_hex=sq_cred.answer_verifier,
                parameters=sq_cred.parameters,
            )
        except Exception as e:
            return AuthenticationResult(
                status=AuthenticationStatus.AUTHENTICATION_UNAVAILABLE,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="VERIFICATION_ERROR",
                metadata={"error": str(e)},
            )

        if not is_correct:
            # INCORRECT ANSWER: TRIGGER 1-HOUR SECURITY LOCKOUT!
            lockout_expires_at = now + ONE_HOUR_SECONDS
            state = self.recovery_store.load_recovery_state(principal_id)
            updated_state = state.model_copy(
                update={
                    "state": RecoveryStateEnum.RECOVERY_LOCKED,
                    "recovery_locked": True,
                    "recovery_locked_at": now,
                    "recovery_lockout_expires_at": lockout_expires_at,
                    "failed_recovery_attempts": state.failed_recovery_attempts + 1,
                    "state_version": state.state_version + 1,
                    "updated_at": now,
                }
            )
            self.recovery_store.save_recovery_state(updated_state)

            # Revoke all active sessions
            revoked_count = self.session_manager.revoke_all_sessions()

            # Invalidate all outstanding challenges for principal
            for cid, chal in list(self._challenges.items()):
                if chal.principal_id == principal_id and not chal.consumed:
                    self._challenges[cid] = chal.model_copy(update={"consumed": True, "consumed_at": now})

            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_ANSWER_FAILED",
                result="RECOVERY_LOCKED",
                correlation_id=correlation_id,
                details={"principal_id": principal_id, "lockout_expires_at": lockout_expires_at},
            )
            self.audit_logger.log_event(
                component="recovery_service",
                action="SECURITY_RECOVERY_LOCKOUT_STARTED",
                result="SUCCESS",
                correlation_id=correlation_id,
                details={"principal_id": principal_id, "duration_seconds": ONE_HOUR_SECONDS, "revoked_sessions": revoked_count},
            )

            if self.event_bus:
                try:
                    self.event_bus.publish_sync(
                        SecurityRecoveryAnswerFailedEvent(
                            correlation_id=correlation_id,
                            payload={"principal_id": principal_id},
                        )
                    )
                    self.event_bus.publish_sync(
                        SecurityRecoveryLockoutStartedEvent(
                            correlation_id=correlation_id,
                            payload={"principal_id": principal_id, "expires_at": lockout_expires_at},
                        )
                    )
                except Exception:
                    pass

            return AuthenticationResult(
                status=AuthenticationStatus.ACCOUNT_LOCKED,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="RECOVERY_LOCKED",
                metadata={
                    "locked": True,
                    "recovery_lockout_expires_at": lockout_expires_at,
                    "message": "Incorrect recovery answer. Account locked for 60 minutes.",
                },
            )

        # CORRECT ANSWER: TRANSITION TO PIN_RESET_REQUIRED
        state = self.recovery_store.load_recovery_state(principal_id)
        updated_state = state.model_copy(
            update={
                "state": RecoveryStateEnum.PIN_RESET_REQUIRED,
                "state_version": state.state_version + 1,
                "updated_at": now,
            }
        )
        self.recovery_store.save_recovery_state(updated_state)

        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_RECOVERY_ANSWER_VERIFIED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id, "challenge_id": challenge_id},
        )
        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_PIN_RESET_REQUIRED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    SecurityRecoveryAnswerVerifiedEvent(
                        correlation_id=correlation_id,
                        payload={"principal_id": principal_id, "challenge_id": challenge_id},
                    )
                )
            except Exception:
                pass

        return AuthenticationResult(
            status=AuthenticationStatus.SUCCESS,
            authenticated=False,
            timestamp=now,
            correlation_id=correlation_id,
            metadata={
                "state": "PIN_RESET_REQUIRED",
                "challenge_id": challenge_id,
                "message": "Recovery answer verified. Please set a new PIN.",
            },
        )

    def complete_pin_reset(self, challenge_id: str, new_pin: str, confirm_new_pin: str, principal_id: str = "user") -> AuthenticationResult:
        """
        Completes mandatory PIN replacement after verified recovery answer.
        Resets PIN, failure counters, and transitions state to NORMAL.
        """
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        now = self._now()

        state = self.recovery_store.load_recovery_state(principal_id)
        if state.state != RecoveryStateEnum.PIN_RESET_REQUIRED:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="INVALID_RECOVERY_STATE",
                metadata={"error": f"Current recovery state ({state.state}) does not permit PIN reset."},
            )

        # Validate new PIN policy & confirmation
        try:
            self.pin_policy.validate_pin_confirmation(new_pin, confirm_new_pin)
        except PinPolicyValidationError as e:
            return AuthenticationResult(
                status=AuthenticationStatus.INVALID_INPUT,
                authenticated=False,
                timestamp=now,
                correlation_id=correlation_id,
                safe_error_code="POLICY_VALIDATION_FAILED",
                metadata={"error": str(e)},
            )

        # Derive and save new PIN credential
        salt_hex, verifier_hex, params = self.pin_hasher.derive_verifier(new_pin)
        existing_cred = self.credential_store.load_credential(principal_id)
        version = existing_cred.credential_version + 1 if existing_cred else 1

        new_cred = PinCredential(
            credential_id=f"pin_{principal_id}",
            principal=principal_id,
            algorithm=params.get("algorithm", "pbkdf2_sha256"),
            salt=salt_hex,
            verifier=verifier_hex,
            parameters=params,
            created_at=now,
            updated_at=now,
            credential_version=version,
            enabled=True,
        )
        self.credential_store.save_credential(new_cred)

        # Reset Lockout States
        self.lockout_manager.store.save_lockout_state(
            self.lockout_manager.store.load_lockout_state(principal_id).model_copy(
                update={"consecutive_failures": 0, "locked": False, "locked_at": None, "updated_at": now}
            )
        )

        updated_state = state.model_copy(
            update={
                "state": RecoveryStateEnum.NORMAL,
                "recovery_locked": False,
                "recovery_locked_at": None,
                "recovery_lockout_expires_at": None,
                "failed_recovery_attempts": 0,
                "state_version": state.state_version + 1,
                "updated_at": now,
            }
        )
        self.recovery_store.save_recovery_state(updated_state)

        # Revoke stale sessions
        self.session_manager.revoke_all_sessions()

        self.audit_logger.log_event(
            component="recovery_service",
            action="SECURITY_PIN_RESET_COMPLETED",
            result="SUCCESS",
            correlation_id=correlation_id,
            details={"principal_id": principal_id},
        )

        if self.event_bus:
            try:
                self.event_bus.publish_sync(
                    SecurityPinResetCompletedEvent(
                        correlation_id=correlation_id,
                        payload={"principal_id": principal_id},
                    )
                )
            except Exception:
                pass

        return AuthenticationResult(
            status=AuthenticationStatus.SUCCESS,
            authenticated=False,
            timestamp=now,
            correlation_id=correlation_id,
            metadata={"message": "PIN reset completed successfully. You may now authenticate with your new PIN."},
        )

    # =========================================================================
    # BATCH 13 BACKWARD COMPATIBILITY STUBS
    # =========================================================================

    def request_recovery(self, principal_id: str = "user") -> dict:
        res, challenge = self.initiate_recovery(principal_id)
        return {
            "supported": True,
            "status": res.status.value,
            "challenge_id": challenge.challenge_id if challenge else None,
        }

    def validate_recovery_context(self, principal_id: str = "user", answers: Optional[dict] = None) -> bool:
        is_rec_locked, _ = self.check_recovery_lockout(principal_id)
        return not is_rec_locked and self.recovery_store.has_question_credential(principal_id)

    def complete_recovery(self, principal_id: str = "user") -> bool:
        raise NotImplementedError("Batch 14 requires complete_pin_reset with valid challenge and new PIN.")


# Backward compatibility alias for Batch 13 interface
LockoutRecoveryService = RecoveryService
