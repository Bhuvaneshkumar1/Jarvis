"""
Authoritative Secret Redaction & Anti-Leakage Utility for JARVIS (Batch 10).
"""

import re
from typing import Dict, Any, Set, Optional


class SecretRedactor:
    """
    Authoritative secret-redaction utility.
    Prevents accidental credential disclosure in logs, tracebacks, audit records, CLI output, and structured payloads.
    Rule: Redacts entire secret values. Never leaves partial previews (first 4 / last 4 chars).
    """

    REDACTED_MARKER = "[REDACTED_SECRET]"
    REDACTED_HEADER_MARKER = "Bearer [REDACTED_TOKEN]"

    # Regex patterns for automated detection & redaction
    PATTERNS = [
        # Bearer tokens
        (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        # Basic authorization
        (re.compile(r"Basic\s+[a-zA-Z0-9+/=]{10,}", re.IGNORECASE), "Basic [REDACTED_CREDENTIALS]"),
        # URL Credentials (e.g. postgres://user:password@host)
        (re.compile(r"://([^:@\s]+):([^@\s]+)@"), "://[REDACTED_USER]:[REDACTED_PASS]@"),
        # Common API keys (OpenAI, GitHub, Slack)
        (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
        (re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
        (re.compile(r"xox[bap]-[a-zA-Z0-9\-]+", re.IGNORECASE), "[REDACTED_SLACK_TOKEN]"),
        # Key-Value assignments (api_key=secret, password="secret")
        (
            re.compile(r"(api[-_]?key|password|token|secret|private[-_]?key)\s*[:=]\s*['\"]?([^'\"\s&,{}]+)['\"]?", re.IGNORECASE),
            r"\1=[REDACTED_SECRET]",
        ),
    ]

    def __init__(self, registered_secrets: Optional[Set[str]] = None):
        self.registered_secrets: Set[str] = registered_secrets or set()

    def register_secret_value(self, raw_secret: str) -> None:
        """Registers a known raw secret string to dynamically sanitize."""
        if raw_secret and isinstance(raw_secret, str) and len(raw_secret.strip()) >= 3:
            self.registered_secrets.add(raw_secret.strip())

    def redact_text(self, text: str) -> str:
        """
        Sanitizes text by replacing known secret values and matching pattern regexes.
        """
        if not text or not isinstance(text, str):
            return text

        result = text

        # 1. Exact replacement of registered raw secrets
        for raw_sec in self.registered_secrets:
            if raw_sec in result:
                result = result.replace(raw_sec, self.REDACTED_MARKER)

        # 2. Regex pattern replacement
        for pattern, replacement in self.PATTERNS:
            result = pattern.sub(replacement, result)

        return result

    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitizes dictionary keys and values.
        Key names matching secret patterns are masked.
        """
        if not isinstance(data, dict):
            return data

        sanitized: Dict[str, Any] = {}
        secret_key_terms = {"password", "secret", "token", "api_key", "apikey", "private_key", "client_secret", "credentials"}

        for k, v in data.items():
            lower_key = str(k).lower()
            if any(term in lower_key for term in secret_key_terms):
                sanitized[k] = self.REDACTED_MARKER
            elif isinstance(v, str):
                sanitized[k] = self.redact_text(v)
            elif isinstance(v, dict):
                sanitized[k] = self.redact_dict(v)
            elif isinstance(v, list):
                sanitized[k] = [self.redact_dict(item) if isinstance(item, dict) else (self.redact_text(item) if isinstance(item, str) else item) for item in v]
            else:
                sanitized[k] = v

        return sanitized

    def redact_exception(self, exc: Exception) -> str:
        """Formats and redacts exception message string."""
        msg = f"{type(exc).__name__}: {str(exc)}"
        return self.redact_text(msg)
