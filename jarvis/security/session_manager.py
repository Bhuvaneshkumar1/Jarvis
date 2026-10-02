"""
Authoritative Session Management Subsystem for JARVIS (Batch 12).
Enforces absolute expiration, inactivity timeout, explicit revocation, and in-memory restart security.
"""

import time
import secrets
from typing import Dict, Optional, List, Callable
from jarvis.security.contracts import AuthSession, AuthenticationContext
from jarvis.core.exceptions import SessionExpiredError, SessionRevokedError


class SessionManager:
    """
    Session Manager handling session lifecycle, cryptographically secure token generation,
    absolute & inactivity expiration, and revocation.
    """

    def __init__(
        self,
        default_ttl_seconds: float = 28800.0,  # 8 hours
        inactivity_timeout_seconds: float = 900.0,  # 15 minutes
        clock_fn: Optional[Callable[[], float]] = None,
    ):
        self.default_ttl_seconds = default_ttl_seconds
        self.inactivity_timeout_seconds = inactivity_timeout_seconds
        self.clock_fn = clock_fn or time.time
        self._sessions: Dict[str, AuthSession] = {}

    def _now(self) -> float:
        return self.clock_fn()

    def create_session(self, principal: str = "user") -> AuthSession:
        """
        Creates a new authenticated session with cryptographically unpredictable session ID.
        """
        now = self._now()
        session_id = f"sess_{secrets.token_urlsafe(32)}"
        expires_at = now + self.default_ttl_seconds

        session = AuthSession(
            session_id=session_id,
            principal=principal,
            created_at=now,
            last_activity_at=now,
            expires_at=expires_at,
            inactivity_timeout=self.inactivity_timeout_seconds,
            authentication_method="PIN",
            authentication_state="AUTHENTICATED",
        )

        self._sessions[session_id] = session
        return session

    def validate_session(self, session_id: str) -> Optional[AuthSession]:
        """
        Validates an existing session. If active, updates last_activity_at and returns the session.
        If expired or revoked, raises SessionExpiredError / SessionRevokedError or returns None.
        """
        if not session_id or not isinstance(session_id, str):
            return None

        session = self._sessions.get(session_id)
        if session is None:
            return None

        now = self._now()

        if session.is_revoked():
            raise SessionRevokedError(f"Session {session_id} has been explicitly revoked.")

        if session.is_expired(now=now):
            raise SessionExpiredError(f"Session {session_id} has expired.")

        # Session is valid: update last_activity_at
        updated_session = session.model_copy(update={"last_activity_at": now})
        self._sessions[session_id] = updated_session
        return updated_session

    def get_session(self, session_id: str) -> Optional[AuthSession]:
        """
        Retrieves a session without updating last_activity_at.
        """
        return self._sessions.get(session_id)

    def revoke_session(self, session_id: str) -> bool:
        """
        Explicitly revokes a session.
        """
        if not session_id or session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        if session.is_revoked():
            return True

        now = self._now()
        revoked_session = session.model_copy(update={"revoked_at": now})
        self._sessions[session_id] = revoked_session
        return True

    def revoke_all_sessions(self) -> int:
        """
        Revokes all active sessions. Returns count of revoked sessions.
        """
        now = self._now()
        count = 0
        for sid, sess in list(self._sessions.items()):
            if not sess.is_revoked():
                self._sessions[sid] = sess.model_copy(update={"revoked_at": now})
                count += 1
        return count

    def list_active_sessions(self) -> List[AuthSession]:
        """
        Returns list of all currently active sessions.
        """
        now = self._now()
        return [sess for sess in self._sessions.values() if sess.is_active(now=now)]

    def get_authentication_context(self, session_id: str) -> AuthenticationContext:
        """
        Builds a trusted AuthenticationContext for PolicyEngine from a valid session ID.
        """
        session = self.validate_session(session_id)
        if session is None:
            raise SessionExpiredError(f"Invalid or missing session: {session_id}")

        return AuthenticationContext(
            principal=session.principal,
            session_id=session.session_id,
            authentication_method=session.authentication_method,
            authenticated_at=session.created_at,
            expires_at=session.expires_at,
            assurance_level="PIN_HIGH",
        )

    def clear(self) -> None:
        """
        Clears all in-memory sessions (simulates restart).
        """
        self._sessions.clear()
