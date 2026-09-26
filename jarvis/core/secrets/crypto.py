"""
Cryptographic Master Key & Authenticated Local Encrypted Secret Store (Batch 10).
"""

import base64
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

from cryptography.fernet import Fernet, InvalidToken
from jarvis.core.exceptions import ConfigurationError, EnvironmentSecurityError
from jarvis.core.secrets.models import SecretClassification, SecretValue, SecretMetadata, SecretSource


class MasterKeyManager:
    """
    Owner of Master Key lifecycle, validation, and loading.
    Master key is 32 url-safe base64 encoded bytes for Fernet authenticated encryption.
    Rule: Master key MUST NEVER be hardcoded in Python files or committed to Git.
    """

    DEFAULT_KEY_FILE = "data/secrets/master.key"

    @staticmethod
    def generate_master_key() -> str:
        """Generates a secure 32-byte URL-safe base64 encoded Fernet key."""
        return Fernet.generate_key().decode("utf-8")

    @classmethod
    def load_master_key(
        cls,
        env_var_name: str = "JARVIS_MASTER_KEY",
        key_file_path: Optional[str] = None,
        auto_create_if_missing: bool = True,
    ) -> str:
        """
        Loads master key from process environment or local key file.
        If missing and auto_create_if_missing is True, generates a new key file securely.
        Raises ConfigurationError or EnvironmentSecurityError if master key is invalid or unreadable.
        """
        # 1. Try process environment variable
        env_key = os.environ.get(env_var_name)
        if env_key:
            s_key = env_key.strip()
            cls.validate_master_key(s_key)
            return s_key

        # 2. Try master key file path
        target_path = Path(key_file_path or cls.DEFAULT_KEY_FILE)
        if target_path.exists():
            try:
                raw_text = target_path.read_text(encoding="utf-8").strip()
                cls.validate_master_key(raw_text)
                return raw_text
            except Exception as exc:
                raise EnvironmentSecurityError(f"Master key file '{target_path}' is corrupted or unreadable: {str(exc)}") from exc

        # 3. Auto-initialize key if enabled
        if auto_create_if_missing:
            return cls.initialize_key_file(target_path)

        raise ConfigurationError(f"Master encryption key not found in environment '{env_var_name}' or file '{target_path}'.")

    @classmethod
    def initialize_key_file(cls, key_path: Path) -> str:
        """Safely creates key directory and key file with atomic write and restrictive permissions."""
        key_path.parent.mkdir(parents=True, exist_ok=True)
        new_key = cls.generate_master_key()

        # Atomic write with temp file
        temp_fd, temp_path_str = tempfile.mkstemp(dir=str(key_path.parent))
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(new_key)
                f.flush()
                os.fsync(f.fileno())

            # Apply restrictive permissions where supported
            cls.restrict_file_permissions(temp_path_str)

            os.replace(temp_path_str, str(key_path))
        except Exception as exc:
            if os.path.exists(temp_path_str):
                os.unlink(temp_path_str)
            raise EnvironmentSecurityError(f"Failed to create master key file '{key_path}': {str(exc)}") from exc

        return new_key

    @staticmethod
    def validate_master_key(key_str: str) -> None:
        """Validates format and decoding of base64 Fernet master key."""
        if not key_str or not isinstance(key_str, str):
            raise ConfigurationError("Master key must be a non-empty string.")
        try:
            raw_bytes = base64.urlsafe_b64decode(key_str.encode("utf-8"))
            if len(raw_bytes) != 32:
                raise ConfigurationError(f"Invalid master key byte length: expected 32 bytes, got {len(raw_bytes)}.")
        except Exception as exc:
            raise ConfigurationError(f"Invalid master key format: {str(exc)}") from exc

    @staticmethod
    def restrict_file_permissions(file_path: str) -> None:
        """Enforces restrictive file permissions (chmod 0600 on POSIX)."""
        if sys.platform != "win32":
            try:
                os.chmod(file_path, 0o600)
            except OSError:
                pass


class EncryptedSecretStore:
    """
    Authenticated Local Encrypted Secret Store using Fernet (AES-128-CBC + HMAC-SHA256).
    Enforces atomic crash-safe writes, versioned metadata, thread safety, and tamper detection.
    """

    FORMAT_VERSION = 1
    DEFAULT_STORE_FILE = "data/secrets/encrypted_store.json"

    def __init__(
        self,
        master_key: str,
        store_path: str = DEFAULT_STORE_FILE,
    ):
        MasterKeyManager.validate_master_key(master_key)
        self.master_key = master_key
        self.fernet = Fernet(master_key.encode("utf-8"))
        self.store_path = Path(store_path)
        self._lock = threading.RLock()

    def _read_raw_store(self) -> Dict[str, Any]:
        """Reads and parses outer store container format."""
        if not self.store_path.exists():
            return {
                "format_version": self.FORMAT_VERSION,
                "created_at": time.time(),
                "updated_at": time.time(),
                "ciphertext": "",
            }

        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "ciphertext" not in data:
                raise EnvironmentSecurityError(f"Encrypted secret store '{self.store_path}' format is invalid.")
            return data
        except Exception as exc:
            if isinstance(exc, EnvironmentSecurityError):
                raise
            raise EnvironmentSecurityError(f"Failed to read encrypted secret store '{self.store_path}': {str(exc)}") from exc

    def _decrypt_payload(self, raw_store: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Decrypts Fernet ciphertext payload into inner secret entries map."""
        ciphertext = raw_store.get("ciphertext", "")
        if not ciphertext:
            return {}

        try:
            decrypted_bytes = self.fernet.decrypt(ciphertext.encode("utf-8"))
            payload = json.loads(decrypted_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                raise EnvironmentSecurityError("Decrypted payload format invalid.")
            return payload
        except InvalidToken as exc:
            raise EnvironmentSecurityError(f"TAMPER DETECTED / WRONG MASTER KEY: Failed to decrypt secret store '{self.store_path}'.") from exc
        except Exception as exc:
            raise EnvironmentSecurityError(f"Failed to decrypt secret payload: {str(exc)}") from exc

    def _write_atomic(self, entries: Dict[str, Dict[str, Any]]) -> None:
        """Encrypts inner payload and performs atomic crash-safe store replacement."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        payload_bytes = json.dumps(entries).encode("utf-8")
        ciphertext_str = self.fernet.encrypt(payload_bytes).decode("utf-8")

        outer_container = {
            "format_version": self.FORMAT_VERSION,
            "updated_at": time.time(),
            "ciphertext": ciphertext_str,
        }

        # Atomic write using temp file and replacement
        temp_fd, temp_path_str = tempfile.mkstemp(dir=str(self.store_path.parent))
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(outer_container, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            MasterKeyManager.restrict_file_permissions(temp_path_str)
            os.replace(temp_path_str, str(self.store_path))
        except Exception as exc:
            if os.path.exists(temp_path_str):
                os.unlink(temp_path_str)
            raise EnvironmentSecurityError(f"Failed to write encrypted secret store '{self.store_path}': {str(exc)}") from exc

    def set_secret(
        self,
        identifier: str,
        value: SecretValue,
        classification: SecretClassification = SecretClassification.SECRET,
    ) -> SecretMetadata:
        """Encrypts and persists secret entry in store."""
        with self._lock:
            raw_store = self._read_raw_store()
            entries = self._decrypt_payload(raw_store)

            now = time.time()
            existing = entries.get(identifier, {})
            new_version = existing.get("version", 0) + 1

            entries[identifier] = {
                "raw_value": value.get_unredacted_value(),
                "classification": classification.value,
                "version": new_version,
                "created_at": existing.get("created_at", now),
                "updated_at": now,
            }

            self._write_atomic(entries)

            meta = SecretMetadata(
                identifier=identifier,
                classification=classification,
                source=SecretSource.ENCRYPTED_STORE,
                present=True,
                valid_format=True,
                fingerprint=value.compute_fingerprint(),
                version=new_version,
                created_at=existing.get("created_at", now),
                updated_at=now,
            )
            return meta

    def get_secret(self, identifier: str) -> Tuple[Optional[SecretValue], Optional[SecretMetadata]]:
        """Decrypts and retrieves secret value and metadata for given identifier."""
        with self._lock:
            raw_store = self._read_raw_store()
            entries = self._decrypt_payload(raw_store)

            if identifier not in entries:
                return None, None

            entry = entries[identifier]
            s_val = SecretValue(entry["raw_value"])
            cls_enum = SecretClassification(entry.get("classification", SecretClassification.SECRET.value))

            meta = SecretMetadata(
                identifier=identifier,
                classification=cls_enum,
                source=SecretSource.ENCRYPTED_STORE,
                present=True,
                valid_format=True,
                fingerprint=s_val.compute_fingerprint(),
                version=entry.get("version", 1),
                created_at=entry.get("created_at", time.time()),
                updated_at=entry.get("updated_at", time.time()),
            )
            return s_val, meta

    def delete_secret(self, identifier: str) -> bool:
        """Deletes secret entry from store if present."""
        with self._lock:
            raw_store = self._read_raw_store()
            entries = self._decrypt_payload(raw_store)

            if identifier not in entries:
                return False

            del entries[identifier]
            self._write_atomic(entries)
            return True

    def list_metadata(self) -> Dict[str, SecretMetadata]:
        """Returns map of secret identifiers to non-sensitive metadata snapshots."""
        with self._lock:
            raw_store = self._read_raw_store()
            entries = self._decrypt_payload(raw_store)

            result: Dict[str, SecretMetadata] = {}
            for k, v in entries.items():
                s_val = SecretValue(v["raw_value"])
                cls_enum = SecretClassification(v.get("classification", SecretClassification.SECRET.value))
                result[k] = SecretMetadata(
                    identifier=k,
                    classification=cls_enum,
                    source=SecretSource.ENCRYPTED_STORE,
                    present=True,
                    valid_format=True,
                    fingerprint=s_val.compute_fingerprint(),
                    version=v.get("version", 1),
                    created_at=v.get("created_at", time.time()),
                    updated_at=v.get("updated_at", time.time()),
                )
            return result
