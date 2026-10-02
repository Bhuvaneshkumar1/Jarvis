"""
Authoritative PIN Lockout Manager & Lockout Recovery Integration Interface for JARVIS (Batch 13).
"""

import time
import threading
from typing import Optional, Tuple, Callable
from jarvis.security.lockout_models import LockoutState, LockoutReason
from jarvis.security.lockout_store import LockoutStore
from jarvis.core.exceptions import AuthorizationError


class LockoutManager:
    """
    Authoritative Lockout Manager enforcing 3-consecutive-failure PIN lockout policy,
    atomic state updates, and persistent lockout tracking across restarts.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        store: Optional[LockoutStore] = None,
        clock_fn: Optional[Callable[[], float]] = None,
    ):
        self.max_attempts = max_attempts
        self.store = store or LockoutStore()
        self.clock_fn = clock_fn or time.time
        self._lock = threading.Lock()

    def _now(self) -> float:
        return self.clock_fn()

    def check_lockout(self, principal_id: str = "user") -> LockoutState:
        """
        Loads and returns the current lockout state for principal.
        """
        return self.store.load_lockout_state(principal_id)

    def record_failure(self, principal_id: str = "user") -> Tuple[LockoutState, bool]:
        """
        Atomically records a failed PIN verification attempt.
        If consecutive failures reach max_attempts (3), transitions state to LOCKED.
        Returns Tuple[updated_state, lockout_just_triggered].
        """
        with self._lock:
            now = self._now()
            current_state = self.store.load_lockout_state(principal_id)

            if current_state.locked:
                # Already locked
                return current_state, False

            new_failures = current_state.consecutive_failures + 1
            lockout_triggered = new_failures >= self.max_attempts

            updated_state = current_state.model_copy(
                update={
                    "consecutive_failures": new_failures,
                    "maximum_attempts": self.max_attempts,
                    "locked": lockout_triggered,
                    "locked_at": now if lockout_triggered else current_state.locked_at,
                    "last_failure_at": now,
                    "lockout_reason": LockoutReason.MAXIMUM_FAILED_ATTEMPTS if lockout_triggered else current_state.lockout_reason,
                    "state_version": current_state.state_version + 1,
                    "updated_at": now,
                }
            )

            self.store.save_lockout_state(updated_state)
            return updated_state, lockout_triggered

    def record_success(self, principal_id: str = "user") -> LockoutState:
        """
        Atomically resets consecutive failure counter upon successful PIN verification.
        Raises AuthorizationError if account is currently locked!
        """
        with self._lock:
            now = self._now()
            current_state = self.store.load_lockout_state(principal_id)

            if current_state.locked:
                raise AuthorizationError("Cannot record successful PIN verification while account is locked.")

            if current_state.consecutive_failures == 0 and current_state.last_success_at is not None:
                # Already clean
                return current_state

            updated_state = current_state.model_copy(
                update={
                    "consecutive_failures": 0,
                    "last_success_at": now,
                    "state_version": current_state.state_version + 1,
                    "updated_at": now,
                }
            )

            self.store.save_lockout_state(updated_state)
            return updated_state


class LockoutRecoveryService:
    """
    Interface / Integration point for Batch 14 Security Question Recovery.
    In Batch 13, recovery methods return unsupported status / raise NotImplementedError.
    """

    def request_recovery(self, principal_id: str = "user") -> dict:
        return {
            "supported": False,
            "status": "NOT_IMPLEMENTED_IN_BATCH_13",
            "message": "Security question recovery workflow is deferred to Batch 14.",
        }

    def validate_recovery_context(self, principal_id: str = "user", answers: Optional[dict] = None) -> bool:
        return False

    def complete_recovery(self, principal_id: str = "user") -> bool:
        raise NotImplementedError("Batch 13 does not allow unauthorized lockout clearing. Security question recovery belongs to Batch 14.")
