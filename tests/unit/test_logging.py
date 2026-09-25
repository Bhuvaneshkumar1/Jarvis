import os
import glob
from jarvis.core.logging import JarvisLogger, redact_sensitive_data

def test_daily_log_filename_format(temp_dir):
    logger = JarvisLogger(component="TestLogger", log_dir=temp_dir)
    logger.info("Test log line")

    logs = glob.glob(os.path.join(temp_dir, "*_log.txt"))
    assert len(logs) == 1
    filename = os.path.basename(logs[0])
    # Verify YYYYMMDD_log.txt format
    assert filename.endswith("_log.txt")
    assert len(filename) == 16  # 8 digits + 8 chars (_log.txt)

def test_secret_redaction():
    raw_msg = "Attempting connect with OPENROUTER_API_KEY=TOKEN_PLACEHOLDER and GITHUB_TOKEN=TOKEN_PLACEHOLDER"
    sanitized = redact_sensitive_data(raw_msg)
    assert "TOKEN_PLACEHOLDER" not in sanitized
    assert "TOKEN_PLACEHOLDER" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
