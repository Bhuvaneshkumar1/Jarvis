import os
import json
from datetime import datetime, timezone
from jarvis.core.audit_log import AuditLogger


def test_daily_log_filename(temp_dir):
    logger = AuditLogger(log_dir=temp_dir)
    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
    filepath = logger.log_event(
        component="TestComponent",
        action="TEST_ACTION",
        result="SUCCESS",
        timestamp=now,
    )
    expected_filename = "20260925_log.txt"
    assert os.path.basename(filepath) == expected_filename
    assert os.path.exists(filepath)


def test_sensitive_data_redaction(temp_dir):
    logger = AuditLogger(log_dir=temp_dir)
    filepath = logger.log_event(
        component="AuthModule",
        action="LOGIN",
        result="SUCCESS",
        details={"api_key": "secret_key_12345", "user": "admin"},
        error="Failed to connect with password=SuperSecretPassword123",
    )
    with open(filepath, "r", encoding="utf-8") as f:
        line = f.readline()
        record = json.loads(line)
        assert record["details"]["api_key"] == "[REDACTED_SENSITIVE_DATA]"
        assert "SuperSecretPassword123" not in record["error"]
        assert "[REDACTED_SENSITIVE_DATA]" in record["error"]
