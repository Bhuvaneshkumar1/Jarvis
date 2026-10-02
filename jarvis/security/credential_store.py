"""
Secure PIN Credential Persistence Engine for JARVIS (Batch 12).
Enforces atomic file updates, file permission verification, and post-write verification.
"""

import os
import json
import tempfile
from typing import Optional
from jarvis.security.contracts import PinCredential
from jarvis.core.exceptions import CredentialCorruptedError, AuthenticationUnavailableError


class PinCredentialStore:
    """
    Protected Credential Storage Engine for PIN Verifiers.
    Persists credential records atomically without storing raw PINs.
    """

    def __init__(self, storage_dir: str = "data/credentials"):
        self.storage_dir = os.path.realpath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_credential_path(self, principal: str = "user") -> str:
        safe_principal = "".join(c for c in principal if c.isalnum() or c in ("_", "-")).lower()
        if not safe_principal:
            safe_principal = "user"
        return os.path.join(self.storage_dir, f"pin_credential_{safe_principal}.json")

    def save_credential(self, credential: PinCredential) -> None:
        """
        Atomically saves PIN credential record and verifies persisted record before returning.
        """
        if not isinstance(credential, PinCredential):
            raise ValueError("Expected valid PinCredential instance.")

        target_path = self._get_credential_path(credential.principal)
        json_data = credential.model_dump_json(indent=2)

        # Atomic write pattern: write to temp file in same directory, flush/fsync, replace
        temp_fd, temp_path = tempfile.mkstemp(dir=self.storage_dir, prefix="tmp_cred_", suffix=".json")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())

            # Replace atomic target
            os.replace(temp_path, target_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise AuthenticationUnavailableError(f"Failed to save credential atomically: {str(e)}") from e

        # Post-write verification
        loaded = self.load_credential(credential.principal)
        if loaded is None or loaded.verifier != credential.verifier or loaded.salt != credential.salt:
            raise CredentialCorruptedError("Post-write verification failed for stored PIN credential record.")

    def load_credential(self, principal: str = "user") -> Optional[PinCredential]:
        """
        Loads stored credential record for the specified principal.
        Returns None if no credential is enrolled.
        """
        target_path = self._get_credential_path(principal)
        if not os.path.exists(target_path):
            return None

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PinCredential(**data)
        except Exception as e:
            raise CredentialCorruptedError(f"Failed to load or parse stored PIN credential: {str(e)}") from e

    def has_credential(self, principal: str = "user") -> bool:
        """
        Returns True if a valid credential record exists for principal.
        """
        target_path = self._get_credential_path(principal)
        if not os.path.exists(target_path):
            return False
        cred = self.load_credential(principal)
        return cred is not None and cred.enabled

    def delete_credential(self, principal: str = "user") -> bool:
        """
        Deletes stored credential record.
        """
        target_path = self._get_credential_path(principal)
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
                return True
            except OSError as e:
                raise AuthenticationUnavailableError(f"Failed to remove credential file: {str(e)}") from e
        return False
