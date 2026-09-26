"""
Comprehensive Unit & Security Hardening Tests for Configuration Trust Boundary (Batch 11).
"""

import os
import pytest
from unittest.mock import patch

from config.settings import Settings
from config.hardening import (
    validate_path_security,
    validate_cross_field_dependencies,
    compute_config_fingerprint,
    enforce_fail_closed_startup,
)
from jarvis.core.exceptions import (
    ConfigurationError,
    EnvironmentSecurityError,
)


# ============================================================================
# 1. DETERMINISTIC PRECEDENCE TESTS
# ============================================================================


def test_configuration_precedence_hierarchy():
    # 1. Defaults -> 2. Process Env -> 3. Explicit Overrides
    with patch.dict(os.environ, {"JARVIS_LOG_LEVEL": "WARNING"}, clear=True):
        # Process env overrides default ("INFO" -> "WARNING")
        s1 = Settings(env_file=None)
        assert s1.logging.log_level == "WARNING"

        # Explicit overrides take highest priority over process env ("WARNING" -> "CRITICAL")
        s2 = Settings(env_file=None, overrides={"JARVIS_LOG_LEVEL": "CRITICAL"})
        assert s2.logging.log_level == "CRITICAL"


# ============================================================================
# 2. PATH BOUNDARY & TRAVERSAL PROTECTION TESTS
# ============================================================================


def test_validate_path_security_traversal_rejection():
    with pytest.raises(EnvironmentSecurityError, match="Path traversal '..' detected"):
        validate_path_security("../../etc/passwd", "TEST_PATH")


def test_validate_path_security_windows_system_dir_rejection():
    if os.name == "nt":
        with pytest.raises(EnvironmentSecurityError, match="collides with protected system directory"):
            validate_path_security("C:\\Windows\\System32\\config.db", "JARVIS_DATABASE_PATH")


def test_validate_path_security_canonical_resolution():
    valid_rel = "data/jarvis_tasks.db"
    resolved = validate_path_security(valid_rel, "JARVIS_DATABASE_PATH")
    assert resolved.is_absolute()
    assert "jarvis_tasks.db" in str(resolved)


# ============================================================================
# 3. CROSS-FIELD DEPENDENCY & PRODUCTION HARDENING TESTS
# ============================================================================


def test_cross_field_production_debug_prohibition():
    with patch.dict(os.environ, {"JARVIS_ENV": "production", "JARVIS_DEBUG": "true"}, clear=True):
        settings = Settings(env_file=None)
        with pytest.raises(EnvironmentSecurityError, match="Debug mode .* is strictly prohibited in production"):
            validate_cross_field_dependencies(settings)


def test_cross_field_resource_limits_conflict():
    with patch.dict(os.environ, {"JARVIS_MAX_MEMORY_GB": "4", "JARVIS_IDLE_MEMORY_TARGET_GB": "8"}, clear=True):
        with pytest.raises(ConfigurationError, match="cannot exceed JARVIS_MAX_MEMORY_GB"):
            Settings(env_file=None)


# ============================================================================
# 4. CONFIGURATION FINGERPRINTING TESTS
# ============================================================================


def test_compute_config_fingerprint_deterministic_and_change_detection():
    with patch.dict(os.environ, {"JARVIS_LOG_LEVEL": "INFO"}, clear=True):
        s1 = Settings(env_file=None)
        fp1 = compute_config_fingerprint(s1)
        assert isinstance(fp1, str)
        assert len(fp1) == 64  # SHA-256 hex string

    with patch.dict(os.environ, {"JARVIS_LOG_LEVEL": "DEBUG"}, clear=True):
        s2 = Settings(env_file=None)
        fp2 = compute_config_fingerprint(s2)
        assert fp1 != fp2  # Modifying log level alters configuration fingerprint


# ============================================================================
# 5. FAIL-CLOSED STARTUP ENFORCEMENT TESTS
# ============================================================================


def test_enforce_fail_closed_startup_valid():
    with patch.dict(os.environ, {"JARVIS_ENV": "development"}, clear=True):
        settings = Settings(env_file=None)
        res = enforce_fail_closed_startup(settings_obj=settings)
        assert res["status"] == "VALIDATED"
        assert len(res["fingerprint"]) == 64


def test_enforce_fail_closed_startup_blocked_on_invalid_combination():
    with patch.dict(os.environ, {"JARVIS_ENV": "production", "JARVIS_DEBUG": "true"}, clear=True):
        settings = Settings(env_file=None)
        with pytest.raises(EnvironmentSecurityError, match="prohibited"):
            enforce_fail_closed_startup(settings_obj=settings)


# ============================================================================
# 6. IMMUTABILITY & HEALTH CHECK TESTS
# ============================================================================


def test_runtime_configuration_immutability():
    settings = Settings(env_file=None)
    with pytest.raises(ConfigurationError, match="Settings object is immutable"):
        settings.app = None  # type: ignore


@pytest.mark.asyncio
async def test_runtime_health_reporting_granularity():
    with patch.dict(os.environ, {"JARVIS_ENV": "test"}, clear=True):
        from jarvis.core.runtime.application import JarvisApplication

        app = JarvisApplication()
        health = await app.get_health()

        assert "runtime_state" in health
        assert "overall_status" in health
        assert "components" in health
        assert "EventBus" in health["components"]
        assert "TaskManager" in health["components"]
        assert "Orchestrator" in health["components"]
