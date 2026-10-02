"""
Persistent & Tamper-Resistant Lockout State Store for JARVIS (Batch 13).
"""

import os
import json
import tempfile
import threading
from jarvis.security.lockout_models import LockoutState
from jarvis.core.exceptions import CredentialCorruptedError, AuthenticationUnavailableError


class LockoutStore:
    """
    Protected Lockout State Store enforcing atomic file updates, process concurrency locks,
    and post-write verification.
    """

    def __init__(self, storage_dir: str = "data/credentials"):
        self.storage_dir = os.path.realpath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _get_lockout_path(self, principal_id: str = "user") -> str:
        safe_principal = "".join(c for c in principal_id if c.isalnum() or c in ("_", "-")).lower()
        if not safe_principal:
            safe_principal = "user"
        return os.path.join(self.storage_dir, f"pin_lockout_{safe_principal}.json")

    def save_lockout_state(self, state: LockoutState) -> None:
        """
        Atomically saves lockout state record to disk and verifies post-write persistence.
        """
        if not isinstance(state, LockoutState):
            raise ValueError("Expected valid LockoutState instance.")

        target_path = self._get_lockout_path(state.principal_id)
        json_data = state.model_dump_json(indent=2)

        with self._lock:
            temp_fd, temp_path = tempfile.mkstemp(dir=self.storage_dir, prefix="tmp_lock_", suffix=".json")
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
                raise AuthenticationUnavailableError(f"Failed to save lockout state atomically: {str(e)}") from e

        # Post-write verification
        loaded = self.load_lockout_state(state.principal_id)
        if loaded is None or loaded.locked != state.locked or loaded.consecutive_failures != state.consecutive_failures:
            raise CredentialCorruptedError("Post-write verification failed for stored lockout state.")

    def load_lockout_state(self, principal_id: str = "user") -> LockoutState:
        """
        Loads stored lockout state. If file does not exist, returns initial unlocked state.
        Raises CredentialCorruptedError if stored record is corrupted or invalid.
        """
        target_path = self._get_lockout_path(principal_id)
        if not os.path.exists(target_path):
            return LockoutState(principal_id=principal_id)

        with self._lock:
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return LockoutState(**data)
            except Exception as e:
                raise CredentialCorruptedError(f"Failed to load or parse stored lockout state: {str(e)}") from e

    def delete_lockout_state(self, principal_id: str = "user") -> bool:
        """
        Deletes stored lockout state file.
        """
        target_path = self._get_lockout_path(principal_id)
        with self._lock:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                    return True
                except OSError as e:
                    raise AuthenticationUnavailableError(f"Failed to remove lockout state file: {str(e)}") from e
            return False
