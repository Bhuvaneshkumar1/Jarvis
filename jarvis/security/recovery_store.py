"""
Persistent Storage Engine for Security Question Credentials and Recovery Lockout State (Batch 14).
"""

import os
import json
import tempfile
import threading
from typing import Optional
from jarvis.security.recovery_models import SecurityQuestionCredential, RecoveryLockoutState
from jarvis.core.exceptions import CredentialCorruptedError, AuthenticationUnavailableError


class RecoveryStore:
    """
    Protected Store handling atomic persistence of Security Question Credentials
    and Recovery Lockout States.
    """

    def __init__(self, storage_dir: str = "data/credentials"):
        self.storage_dir = os.path.realpath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _get_question_path(self, principal_id: str = "user") -> str:
        safe_principal = "".join(c for c in principal_id if c.isalnum() or c in ("_", "-")).lower()
        if not safe_principal:
            safe_principal = "user"
        return os.path.join(self.storage_dir, f"pin_question_{safe_principal}.json")

    def _get_recovery_lockout_path(self, principal_id: str = "user") -> str:
        safe_principal = "".join(c for c in principal_id if c.isalnum() or c in ("_", "-")).lower()
        if not safe_principal:
            safe_principal = "user"
        return os.path.join(self.storage_dir, f"pin_recovery_lockout_{safe_principal}.json")

    # =========================================================================
    # Security Question Credential Methods
    # =========================================================================

    def save_question_credential(self, credential: SecurityQuestionCredential) -> None:
        if not isinstance(credential, SecurityQuestionCredential):
            raise ValueError("Expected valid SecurityQuestionCredential instance.")

        target_path = self._get_question_path(credential.principal_id)
        json_data = credential.model_dump_json(indent=2)

        with self._lock:
            temp_fd, temp_path = tempfile.mkstemp(dir=self.storage_dir, prefix="tmp_sq_", suffix=".json")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(json_data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, target_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                raise AuthenticationUnavailableError(f"Failed to save security question credential: {str(e)}") from e

        loaded = self.load_question_credential(credential.principal_id)
        if loaded is None or loaded.answer_verifier != credential.answer_verifier:
            raise CredentialCorruptedError("Post-write verification failed for stored security question credential.")

    def load_question_credential(self, principal_id: str = "user") -> Optional[SecurityQuestionCredential]:
        target_path = self._get_question_path(principal_id)
        if not os.path.exists(target_path):
            return None

        with self._lock:
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SecurityQuestionCredential(**data)
            except Exception as e:
                raise CredentialCorruptedError(f"Failed to load security question credential: {str(e)}") from e

    def has_question_credential(self, principal_id: str = "user") -> bool:
        target_path = self._get_question_path(principal_id)
        if not os.path.exists(target_path):
            return False
        cred = self.load_question_credential(principal_id)
        return cred is not None

    def delete_question_credential(self, principal_id: str = "user") -> bool:
        target_path = self._get_question_path(principal_id)
        with self._lock:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                    return True
                except OSError as e:
                    raise AuthenticationUnavailableError(f"Failed to delete security question credential: {str(e)}") from e
            return False

    # =========================================================================
    # Recovery Lockout State Methods
    # =========================================================================

    def save_recovery_state(self, state: RecoveryLockoutState) -> None:
        if not isinstance(state, RecoveryLockoutState):
            raise ValueError("Expected valid RecoveryLockoutState instance.")

        target_path = self._get_recovery_lockout_path(state.principal_id)
        json_data = state.model_dump_json(indent=2)

        with self._lock:
            temp_fd, temp_path = tempfile.mkstemp(dir=self.storage_dir, prefix="tmp_rec_lock_", suffix=".json")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(json_data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, target_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                raise AuthenticationUnavailableError(f"Failed to save recovery lockout state: {str(e)}") from e

        loaded = self.load_recovery_state(state.principal_id)
        if loaded is None or loaded.state != state.state or loaded.recovery_locked != state.recovery_locked:
            raise CredentialCorruptedError("Post-write verification failed for stored recovery lockout state.")

    def load_recovery_state(self, principal_id: str = "user") -> RecoveryLockoutState:
        target_path = self._get_recovery_lockout_path(principal_id)
        if not os.path.exists(target_path):
            return RecoveryLockoutState(principal_id=principal_id)

        with self._lock:
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return RecoveryLockoutState(**data)
            except Exception as e:
                raise CredentialCorruptedError(f"Failed to load stored recovery lockout state: {str(e)}") from e
