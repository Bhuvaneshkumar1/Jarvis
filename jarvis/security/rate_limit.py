"""
Rate-Limiting Foundation & Attempt Tracking Primitive for JARVIS Authentication (Batch 12).
Prepares infrastructure for Batch 13 brute-force lockout without enforcing lockout premature policy.
"""

import time
from typing import Dict, List, Optional, Callable


class AttemptTracker:
    """
    Tracks failed verification attempts, timestamps, and failure counters per principal.
    Supports injectable clock for deterministic testing.
    """

    def __init__(self, window_seconds: float = 900.0, clock_fn: Optional[Callable[[], float]] = None):
        self.window_seconds = window_seconds
        self.clock_fn = clock_fn or time.time
        self._attempts: Dict[str, List[float]] = {}

    def _now(self) -> float:
        return self.clock_fn()

    def record_failure(self, principal: str = "user") -> int:
        """
        Records a failed authentication attempt for principal. Returns active attempt count in window.
        """
        now = self._now()
        if principal not in self._attempts:
            self._attempts[principal] = []

        self._attempts[principal].append(now)
        self._cleanup(principal, now)
        return len(self._attempts[principal])

    def record_success(self, principal: str = "user") -> None:
        """
        Resets failed attempt counter upon successful authentication.
        """
        if principal in self._attempts:
            self._attempts[principal].clear()

    def get_failed_attempts(self, principal: str = "user") -> int:
        """
        Returns number of recorded failed attempts within the active time window.
        """
        now = self._now()
        self._cleanup(principal, now)
        return len(self._attempts.get(principal, []))

    def reset_attempts(self, principal: str = "user") -> None:
        """
        Resets attempt history for a principal.
        """
        if principal in self._attempts:
            self._attempts[principal].clear()

    def _cleanup(self, principal: str, now: float) -> None:
        if principal in self._attempts:
            cutoff = now - self.window_seconds
            self._attempts[principal] = [t for t in self._attempts[principal] if t >= cutoff]
