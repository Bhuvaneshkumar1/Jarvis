"""
Deterministic Answer Normalization and Cryptographic Hasher for Recovery Answers (Batch 14).
"""

import re
import hmac
import secrets
import unicodedata
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jarvis.core.exceptions import AuthenticationUnavailableError, CredentialCorruptedError

DEFAULT_ITERATIONS = 210000
SALT_SIZE_BYTES = 32
KEY_LENGTH_BYTES = 32


def normalize_answer(answer: str) -> str:
    """
    Deterministically normalizes recovery answer string.
    Steps:
    1. Validate non-null string.
    2. Strip leading and trailing whitespace.
    3. Collapse internal whitespace sequences to single space.
    4. Normalize Unicode representation (NFKC).
    5. Convert to lowercase using casefold().
    """
    if answer is None or not isinstance(answer, str):
        raise ValueError("Recovery answer must be a non-null string instance.")

    cleaned = answer.strip()
    if len(cleaned) == 0:
        raise ValueError("Recovery answer cannot be empty or whitespace-only.")

    # Collapse internal whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Unicode NFKC normalization
    cleaned = unicodedata.normalize("NFKC", cleaned)

    # Case folding
    return cleaned.casefold()


class RecoveryAnswerHasher:
    """
    Cryptographic Key Derivation Function (KDF) Engine for Recovery Answer Verifiers.
    Uses PBKDF2-HMAC-SHA256 with deterministic normalization and constant-time digest comparison.
    """

    def __init__(self, iterations: int = DEFAULT_ITERATIONS):
        self.iterations = iterations

    def derive_answer_verifier(self, answer: str, salt_bytes: Optional[bytes] = None) -> Tuple[str, str, Dict[str, Any]]:
        """
        Derives salt and verifier from normalized recovery answer.
        Returns (salt_hex, verifier_hex, parameters_dict).
        """
        normalized = normalize_answer(answer)

        if salt_bytes is None:
            salt_bytes = secrets.token_bytes(SALT_SIZE_BYTES)

        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_LENGTH_BYTES,
                salt=salt_bytes,
                iterations=self.iterations,
            )
            derived = kdf.derive(normalized.encode("utf-8"))
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
            raise AuthenticationUnavailableError(f"Failed to derive recovery answer verifier: {str(e)}") from e

    def verify_answer(self, candidate_answer: str, salt_hex: str, stored_verifier_hex: str, parameters: Dict[str, Any]) -> bool:
        """
        Performs constant-time comparison between normalized candidate answer verifier and stored verifier.
        """
        if candidate_answer is None or not isinstance(candidate_answer, str):
            return False

        try:
            normalized_candidate = normalize_answer(candidate_answer)
        except ValueError:
            return False

        if not salt_hex or not stored_verifier_hex:
            raise CredentialCorruptedError("Stored salt or verifier is missing for recovery answer.")

        try:
            salt_bytes = bytes.fromhex(salt_hex)
        except ValueError as e:
            raise CredentialCorruptedError(f"Stored recovery salt hex representation is corrupted: {str(e)}") from e

        iterations = parameters.get("iterations", self.iterations) if parameters else self.iterations

        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_LENGTH_BYTES,
                salt=salt_bytes,
                iterations=iterations,
            )
            candidate_derived = kdf.derive(normalized_candidate.encode("utf-8"))
            candidate_verifier_hex = candidate_derived.hex()

            return hmac.compare_digest(candidate_verifier_hex, stored_verifier_hex)
        except CredentialCorruptedError:
            raise
        except Exception as e:
            raise AuthenticationUnavailableError(f"Error during recovery answer verification: {str(e)}") from e
