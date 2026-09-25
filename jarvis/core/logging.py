import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

SENSITIVE_PATTERNS = [
    r"sk-or-v1-[a-zA-Z0-9]+",
    r"sk-[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{30,}",
    r"github_pat_[a-zA-Z0-9_]+",
    r"xox[e|-][a-zA-Z0-9\.\-]+",
    r"cfut_[a-zA-Z0-9]+",
    r"nvapi-[a-zA-Z0-9_]+",
    r"xai-[a-zA-Z0-9]+",
    r"pcsk_[a-zA-Z0-9_]+",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"password\s*[:=]\s*['\"]?([^'\"\s]+)['\"]?",
    r"api[-_]?key\s*[:=]\s*['\"]?([^'\"\s]+)['\"]?",
]

_compiled_regexes = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]

def redact_sensitive_data(text: str) -> str:
    """Sanitizes text strings by replacing credential matches with redaction placeholders."""
    if not text:
        return text
    sanitized = text
    for regex in _compiled_regexes:
        sanitized = regex.sub("[REDACTED_SECRET]", sanitized)
    return sanitized

class RedactingFormatter(logging.Formatter):
    """Logging Formatter that automatically sanitizes log records."""

    def format(self, record: logging.LogRecord) -> str:
        original_msg = super().format(record)
        return redact_sensitive_data(original_msg)

class JarvisLogger:
    """
    Reusable Logging Interface for JARVIS.
    Enforces daily file logging format (YYYYMMDD_log.txt) and secret redaction.
    """

    def __init__(self, component: str = "Core", log_dir: str = "logs"):
        self.component = component
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.logger = logging.getLogger(f"jarvis.{component}")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []

        # Setup daily file handler
        now = datetime.now(timezone.utc)
        filename = now.strftime("%Y%m%d") + "_log.txt"
        log_filepath = os.path.join(self.log_dir, filename)

        file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def log(
        self,
        level: str,
        message: str,
        correlation_id: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ):
        cid_str = f" [cid={correlation_id}]" if correlation_id else ""
        extra_str = f" | {extra_fields}" if extra_fields else ""
        formatted_message = f"{message}{cid_str}{extra_str}"

        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, formatted_message)

    def info(self, message: str, correlation_id: Optional[str] = None):
        self.log("INFO", message, correlation_id=correlation_id)

    def warning(self, message: str, correlation_id: Optional[str] = None):
        self.log("WARNING", message, correlation_id=correlation_id)

    def error(self, message: str, correlation_id: Optional[str] = None):
        self.log("ERROR", message, correlation_id=correlation_id)
