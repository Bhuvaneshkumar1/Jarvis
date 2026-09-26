"""
Unit & Security Tests for Environment Security, .env Validation & Hardening Subsystem (Batch 9).
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from config.env_security import (
    parse_and_validate_env_file,
    verify_git_and_file_security,
    detect_environment_drift,
    enforce_environment_security,
    scan_repository_for_secrets,
    get_environment_diagnostics,
    is_secret_variable,
)
from jarvis.core.exceptions import (
    EnvironmentValidationError,
    EnvironmentSecurityError,
)


# ============================================================================
# 1. PARSING & SYNTAX TESTS
# ============================================================================


def test_parse_valid_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# Comment line\nJARVIS_ENV=development\nJARVIS_LOG_LEVEL=INFO\nHOST="127.0.0.1"\n',
        encoding="utf-8",
    )
    parsed, warnings = parse_and_validate_env_file(env_file)
    assert parsed["JARVIS_ENV"] == "development"
    assert parsed["JARVIS_LOG_LEVEL"] == "INFO"
    assert parsed["HOST"] == "127.0.0.1"


def test_parse_duplicate_variable_rejection(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JARVIS_ENV=development\nJARVIS_ENV=production\n",
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentValidationError, match="Duplicate environment variable"):
        parse_and_validate_env_file(env_file)


def test_parse_malformed_entry_missing_equals(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JARVIS_ENV_DEVELOPMENT\n",
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentValidationError, match="Missing '=' assignment"):
        parse_and_validate_env_file(env_file)


def test_parse_malformed_key_identifier(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "123_INVALID_KEY=value\n",
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentValidationError, match="invalid key name"):
        parse_and_validate_env_file(env_file)


# ============================================================================
# 2. SECRET CLASSIFICATION & DETECTION TESTS
# ============================================================================


def test_is_secret_variable_classification():
    assert is_secret_variable("NVIDIA_API_KEY") is True
    assert is_secret_variable("OPENROUTER_API_KEY") is True
    assert is_secret_variable("MY_CUSTOM_SECRET") is True
    assert is_secret_variable("BOT_TOKEN") is True
    assert is_secret_variable("JARVIS_ENV") is False
    assert is_secret_variable("HOST") is False


# ============================================================================
# 3. DRIFT & UNKNOWN VARIABLE TESTS
# ============================================================================


def test_detect_unknown_jarvis_variable():
    env_dict = {
        "JARVIS_ENV": "development",
        "JARVIS_UNKNOWN_CUSTOM_SETTING": "test",
    }
    drift = detect_environment_drift(env_dict)
    assert "JARVIS_UNKNOWN_CUSTOM_SETTING" in drift["unknown_jarvis_vars"]


def test_detect_missing_required_variable():
    env_dict = {}
    with patch.dict(os.environ, {}, clear=True):
        drift = detect_environment_drift(env_dict)
        assert "JARVIS_ENV" in drift["missing_required"]


# ============================================================================
# 4. SECURITY POLICY ENFORCEMENT TESTS
# ============================================================================


def test_production_debug_prohibition():
    env_dict = {
        "JARVIS_ENV": "production",
        "JARVIS_DEBUG": "true",
    }
    with pytest.raises(EnvironmentSecurityError, match="JARVIS_DEBUG=true is prohibited"):
        enforce_environment_security(env_dict)


def test_production_path_traversal_prohibition():
    env_dict = {
        "JARVIS_ENV": "production",
        "JARVIS_DEBUG": "false",
        "JARVIS_DATABASE_PATH": "../../../etc/passwd",
    }
    with pytest.raises(EnvironmentSecurityError, match="Path traversal '..'"):
        enforce_environment_security(env_dict)


def test_shell_injection_character_rejection():
    env_dict = {
        "JARVIS_LOG_LEVEL": "INFO; rm -rf /",
    }
    with pytest.raises(EnvironmentSecurityError, match="prohibited shell meta-character"):
        enforce_environment_security(env_dict)


# ============================================================================
# 5. GIT TRACKING & REPOSITORY SECRET SCANNING TESTS
# ============================================================================


def test_git_tracking_env_file_blocking(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=".env\n")
        env_file = tmp_path / ".env"
        env_file.write_text("JARVIS_ENV=development", encoding="utf-8")
        with pytest.raises(EnvironmentSecurityError, match="tracked by Git"):
            verify_git_and_file_security(tmp_path)


def test_repository_secret_scanner_synthetic_detection(tmp_path):
    # Create fake source file with dummy secret
    src_file = tmp_path / "bad_module.py"
    prefix = "ghp_"
    fake_token = prefix + "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    src_file.write_text(
        f'API_KEY = "{fake_token}"\n',
        encoding="utf-8",
    )
    findings = scan_repository_for_secrets(tmp_path)
    assert len(findings) >= 1
    assert findings[0].rule_name == "GitHub Token"


# ============================================================================
# 6. DIAGNOSTICS SNAPSHOT & REDACTION TESTS
# ============================================================================


def test_get_environment_diagnostics_sanitization(tmp_path):
    env_file = tmp_path / ".env"
    fake_secret = "TEST_SECRET_DO_NOT_EXPOSE_999"
    env_file.write_text(
        f"JARVIS_ENV=development\nNVIDIA_API_KEY={fake_secret}\n",
        encoding="utf-8",
    )
    snapshot = get_environment_diagnostics(env_file)
    assert "JARVIS ENVIRONMENT SECURITY SNAPSHOT" in snapshot
    assert "NVIDIA_API_KEY (FUTURE): SET" in snapshot
    assert fake_secret not in snapshot


# ============================================================================
# 7. RUNTIME INTEGRATION & STARTUP BLOCKING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_runtime_startup_blocked_on_environment_security_failure():
    with patch.dict(os.environ, {"JARVIS_ENV": "production", "JARVIS_DEBUG": "true"}, clear=True):
        from jarvis.core.runtime.application import JarvisApplication
        from jarvis.core.enums import RuntimeState

        app = JarvisApplication()
        with pytest.raises(EnvironmentSecurityError, match="JARVIS_DEBUG=true is prohibited"):
            await app.start()
        assert app.state == RuntimeState.FAILED
