"""
Unit Tests for Authoritative Centralized Configuration Management System (Batch 8).
"""

import os
import pytest
from unittest.mock import patch
from config.settings import (
    Settings,
    get_settings,
    AppEnvironment,
    parse_bool,
    parse_int,
    parse_float,
)
from jarvis.core.exceptions import ConfigurationError
from jarvis.core.enums import TaskPriority


# ============================================================================
# 1. BOOLEAN PARSING TESTS
# ============================================================================


def test_parse_bool_valid_truthy():
    assert parse_bool(True) is True
    assert parse_bool(1) is True
    assert parse_bool("true") is True
    assert parse_bool("TRUE") is True
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("YES") is True
    assert parse_bool("on") is True
    assert parse_bool("ON") is True


def test_parse_bool_valid_falsy():
    assert parse_bool(False) is False
    assert parse_bool(0) is False
    assert parse_bool("false") is False
    assert parse_bool("FALSE") is False
    assert parse_bool("0") is False
    assert parse_bool("no") is False
    assert parse_bool("NO") is False
    assert parse_bool("off") is False
    assert parse_bool("OFF") is False


def test_parse_bool_invalid_ambiguous():
    with pytest.raises(ConfigurationError, match="Invalid boolean value"):
        parse_bool("maybe")

    with pytest.raises(ConfigurationError, match="numeric value must be 1 or 0"):
        parse_bool(42)

    with pytest.raises(ConfigurationError, match="Invalid boolean type"):
        parse_bool([True])


# ============================================================================
# 2. NUMBER PARSING AND RANGE VALIDATION TESTS
# ============================================================================


def test_parse_int_valid_and_bounds():
    assert parse_int("10", "VAR", min_val=1, max_val=100) == 10
    assert parse_int(50, "VAR", min_val=1, max_val=100) == 50


def test_parse_int_invalid_format():
    with pytest.raises(ConfigurationError, match="Must be an integer"):
        parse_int("abc", "VAR_INT")


def test_parse_int_out_of_range():
    with pytest.raises(ConfigurationError, match="below minimum threshold"):
        parse_int("0", "VAR_INT", min_val=1)

    with pytest.raises(ConfigurationError, match="exceeds maximum allowed limit"):
        parse_int("2000", "VAR_INT", max_val=1000)


def test_parse_float_valid_and_bounds():
    assert parse_float("10.5", "VAR_FLOAT", min_val=0.1, max_val=100.0) == 10.5


def test_parse_float_invalid_format():
    with pytest.raises(ConfigurationError, match="Must be a number"):
        parse_float("not_a_float", "VAR_FLOAT")


# ============================================================================
# 3. PRECEDENCE & LOADING TESTS
# ============================================================================


def test_configuration_defaults():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(env_file=None)
        assert settings.app.environment == AppEnvironment.DEVELOPMENT
        assert settings.app.application_name == "JARVIS"
        assert settings.app.debug is False
        assert settings.logging.log_level == "INFO"
        assert settings.resource.max_memory_gb == 8
        assert settings.task.default_priority == TaskPriority.MEDIUM


def test_configuration_precedence_env_overrides_defaults():
    env_vars = {
        "JARVIS_ENV": "production",
        "JARVIS_LOG_LEVEL": "WARNING",
        "JARVIS_MAX_MEMORY_GB": "16",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(env_file=None)
        assert settings.app.environment == AppEnvironment.PRODUCTION
        assert settings.logging.log_level == "WARNING"
        assert settings.resource.max_memory_gb == 16


def test_configuration_runtime_overrides():
    env_vars = {"JARVIS_LOG_LEVEL": "INFO"}
    overrides = {"JARVIS_LOG_LEVEL": "ERROR"}
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(env_file=None, overrides=overrides)
        assert settings.logging.log_level == "ERROR"


# ============================================================================
# 4. ENUM & RANGE VALIDATION IN SETTINGS
# ============================================================================


def test_invalid_environment_enum():
    with patch.dict(os.environ, {"JARVIS_ENV": "invalid_env"}, clear=True):
        with pytest.raises(ConfigurationError, match="Invalid JARVIS_ENV value"):
            Settings(env_file=None)


def test_invalid_log_level_enum():
    with patch.dict(os.environ, {"JARVIS_LOG_LEVEL": "VERBOSE"}, clear=True):
        with pytest.raises(ConfigurationError, match="Invalid JARVIS_LOG_LEVEL"):
            Settings(env_file=None)


def test_idle_memory_exceeds_max_memory():
    env_vars = {
        "JARVIS_MAX_MEMORY_GB": "4",
        "JARVIS_IDLE_MEMORY_TARGET_GB": "8",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        with pytest.raises(ConfigurationError, match="cannot exceed JARVIS_MAX_MEMORY_GB"):
            Settings(env_file=None)


# ============================================================================
# 5. IMMUTABILITY TESTS
# ============================================================================


def test_settings_immutability():
    settings = Settings(env_file=None)
    with pytest.raises(ConfigurationError, match="Settings object is immutable"):
        settings.app = None  # type: ignore

    with pytest.raises(ConfigurationError, match="Settings object is immutable"):
        settings.env = "test"  # type: ignore


# ============================================================================
# 6. SECRET REDACTION & DIAGNOSTIC LEAK TESTS
# ============================================================================


def test_secret_redaction_and_diagnostics():
    fake_secret = "TEST_FAKE_SECRET_DO_NOT_USE_9999"
    env_vars = {
        "NVIDIA_API_KEY": fake_secret,
        "OPENROUTER_API_KEY": fake_secret,
    }
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(env_file=None)
        assert settings.secrets.nvidia_api_key == fake_secret

        summary = settings.get_sanitized_summary()
        assert summary["secrets"]["NVIDIA_API_KEY"] == "SET"
        assert summary["secrets"]["OPENAI_API_KEY"] == "NOT SET"
        assert fake_secret not in str(summary)

        snapshot = settings.get_diagnostics_snapshot()
        assert "NVIDIA_API_KEY: SET" in snapshot
        assert "OPENAI_API_KEY: NOT SET" in snapshot
        assert fake_secret not in snapshot


# ============================================================================
# 7. SINGLETON GET_SETTINGS LOADER
# ============================================================================


def test_get_settings_singleton_and_reload():
    s1 = get_settings(env_file=None, force_reload=True)
    s2 = get_settings(env_file=None, force_reload=False)
    assert s1 is s2

    s3 = get_settings(env_file=None, force_reload=True)
    assert s3 is not s1


# ============================================================================
# 8. RUNTIME LIFECYCLE INTEGRATION & FAILURE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_runtime_startup_with_valid_config():
    with patch.dict(os.environ, {"JARVIS_ENV": "test"}, clear=True):
        settings = get_settings(env_file=None, force_reload=True)
        from jarvis.core.runtime.application import JarvisApplication
        from jarvis.core.enums import RuntimeState

        app = JarvisApplication(settings=settings)
        await app.start()
        assert app.state == RuntimeState.RUNNING
        await app.shutdown()
        assert app.state == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_runtime_startup_blocked_on_invalid_config():
    with patch.dict(os.environ, {"JARVIS_LOG_LEVEL": "INVALID_LOG_LEVEL"}, clear=True):
        with pytest.raises(ConfigurationError, match="Invalid JARVIS_LOG_LEVEL"):
            # Attempting to load config for runtime fails
            get_settings(env_file=None, force_reload=True)
