import os
import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

DEFAULT_REDACTION_PATTERNS = [
    r"api[-_]?key\s*=\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?",
    r"bearer\s+([a-zA-Z0-9_\-\.]+)",
    r"token\s*=\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?",
    r"password\s*=\s*['\"]?([^'\"\s]+)['\"]?",
    r"secret\s*=\s*['\"]?([^'\"\s]+)['\"]?",
]

class AuditLogger:
    """
    Immutable Daily Audit Logger enforcing Rule 18 & Rule 19.
    Logs to YYYYMMDD_log.txt with automatic redaction of sensitive credentials.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.redaction_regexes = [re.compile(p, re.IGNORECASE) for p in DEFAULT_REDACTION_PATTERNS]

    def _get_log_filepath(self, dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now(timezone.utc)
        filename = dt.strftime("%Y%m%d") + "_log.txt"
        return os.path.join(self.log_dir, filename)

    def redact_text(self, text: str) -> str:
        if not text:
            return text
        redacted = text
        for regex in self.redaction_regexes:
            redacted = regex.sub(r"[REDACTED_SENSITIVE_DATA]", redacted)
        return redacted

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(k in key_lower for k in ["key", "secret", "password", "token", "auth", "credential"]):
                cleaned[key] = "[REDACTED_SENSITIVE_DATA]"
            elif isinstance(value, str):
                cleaned[key] = self.redact_text(value)
            elif isinstance(value, dict):
                cleaned[key] = self._redact_dict(value)
            else:
                cleaned[key] = value
        return cleaned

    def log_event(
        self,
        component: str,
        action: str,
        result: str,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        verification_state: str = "UNVERIFIED",
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        filepath = self._get_log_filepath(timestamp)

        safe_details = self._redact_dict(details) if details else {}
        safe_error = self.redact_text(error) if error else None

        entry = {
            "timestamp": timestamp.isoformat(),
            "task_id": task_id or "N/A",
            "correlation_id": correlation_id or "N/A",
            "agent_id": agent_id or "N/A",
            "component": component,
            "action": action,
            "result": result,
            "verification_state": verification_state,
            "error": safe_error,
            "details": safe_details,
        }

        log_line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(log_line)

        return filepath
