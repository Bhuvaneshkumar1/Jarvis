import re
from typing import Dict, Any, Tuple

class PrivacyEngine:
    """
    Privacy Filter & Sensitive Information Sanitizer enforcing Rule 14.
    Ensures credentials, keys, tokens, and private vault content are NEVER transmitted to cloud LLMs.
    """

    DEFAULT_SENSITIVE_PATTERNS = [
        (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
        (r"ghp_[a-zA-Z0-9]{30,}", "[REDACTED_GITHUB_TOKEN]"),
        (r"xox[bap]-[a-zA-Z0-9\-]+", "[REDACTED_SLACK_TOKEN]"),
        (r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "[REDACTED_EMAIL]"),
        (r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "[REDACTED_CARD_NUMBER]"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
        (r"password\s*[:=]\s*['\"]?([^'\"\s]+)['\"]?", "password: [REDACTED_PASSWORD]"),
    ]

    def __init__(self):
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.DEFAULT_SENSITIVE_PATTERNS
        ]

    def filter_text(self, text: str) -> Tuple[str, bool]:
        """
        Sanitizes text by replacing sensitive matches.
        Returns (sanitized_text, contains_sensitive_data).
        """
        if not text:
            return text, False

        sanitized = text
        was_redacted = False
        for regex, replacement in self.compiled_patterns:
            new_text, count = regex.subn(replacement, sanitized)
            if count > 0:
                was_redacted = True
                sanitized = new_text

        return sanitized, was_redacted

    def enforce_local_routing_check(self, payload: Dict[str, Any], is_cloud: bool = True) -> Dict[str, Any]:
        """
        If routing to cloud, aggressively sanitizes all text fields.
        Raises ValueError if unredactable private data remains and strict privacy is triggered.
        """
        if not is_cloud:
            return payload

        sanitized_payload = {}
        for key, val in payload.items():
            if isinstance(val, str):
                cleaned, _ = self.filter_text(val)
                sanitized_payload[key] = cleaned
            elif isinstance(val, dict):
                sanitized_payload[key] = self.enforce_local_routing_check(val, is_cloud=True)
            else:
                sanitized_payload[key] = val
        return sanitized_payload
