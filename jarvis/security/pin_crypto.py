"""
PIN Cryptographic Primitives & Verifier Engine for JARVIS (Batch 12).
"""

import hmac
import secrets
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jarvis.core.exceptions import AuthenticationUnavailableError, CredentialCorruptedError

DEFAULT_ITERATIONS = 210000
SALT_SIZE_BYTES = 32
KEY_LENGTH_BYTES = 32


class PINHasher:
    """
    Cryptographic Key Derivation Function (KDF) Engine for PIN Verifiers.
    Uses PBKDF2-HMAC-SHA256 with cryptographically secure salts and constant-time digest comparison.
    """

    def __init__(self, iterations: int = DEFAULT_ITERATIONS):
        self.iterations = iterations

    def derive_verifier(self, pin: str, salt_bytes: Optional[bytes] = None) -> Tuple[str, str, Dict[str, Any]]:
        """
        Derives a secure verifier from a PIN candidate.
        Returns (salt_hex, verifier_hex, parameters_dict).
        """
        if not pin or not isinstance(pin, str):
            raise ValueError("PIN candidate must be a non-empty string.")

        if salt_bytes is None:
            salt_bytes = secrets.token_bytes(SALT_SIZE_BYTES)

        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_LENGTH_BYTES,
                salt=salt_bytes,
                iterations=self.iterations,
            )
            derived = kdf.derive(pin.encode("utf-8"))
            salt_hex = salt_bytes.hex()
            verifier_hex = derived.hex()
            parameters = {
                "algorithm": "pbkdf2_sha256",
                "iterations": self.iterations,
                "salt_len": len(salt_bytes),
                "key_len": KEY_LENGTH_BYTES,
            }
            return salt_hex, verifier_hex, parameters
        except Exception as e:
            raise AuthenticationUnavailableError(f"Failed to derive PIN verifier due to cryptographic error: {str(e)}") from e

    def verify_pin(self, candidate_pin: str, salt_hex: str, stored_verifier_hex: str, parameters: Dict[str, Any]) -> bool:
        """
        Performs constant-time comparison between derived candidate verifier and stored verifier.
        """
        if not candidate_pin or not isinstance(candidate_pin, str):
            return False

        if not salt_hex or not stored_verifier_hex:
            raise CredentialCorruptedError("Stored salt or verifier is missing or invalid.")

        try:
            salt_bytes = bytes.fromhex(salt_hex)
        except ValueError as e:
            raise CredentialCorruptedError(f"Stored salt hex representation is corrupted: {str(e)}") from e

        iterations = parameters.get("iterations", self.iterations) if parameters else self.iterations

        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_LENGTH_BYTES,
                salt=salt_bytes,
                iterations=iterations,
            )
            candidate_derived = kdf.derive(candidate_pin.encode("utf-8"))
            candidate_verifier_hex = candidate_derived.hex()

            # Constant-time comparison to prevent timing side-channel attacks
            return hmac.compare_digest(candidate_verifier_hex, stored_verifier_hex)
        except CredentialCorruptedError:
            raise
        except Exception as e:
            raise AuthenticationUnavailableError(f"Error during PIN verification operation: {str(e)}") from e
