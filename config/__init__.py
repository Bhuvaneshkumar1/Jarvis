"""
JARVIS Centralized Configuration & Environment Security Management Package (Batches 8 & 9).
"""

from config.settings import (
    Settings,
    get_settings,
    AppEnvironment,
)
from config.env_security import (
    VarClassification,
    EnvScope,
    EnvVarDef,
    ENV_REGISTRY,
    validate_environment,
    get_environment_diagnostics,
    parse_and_validate_env_file,
    verify_git_and_file_security,
    detect_environment_drift,
    enforce_environment_security,
    scan_repository_for_secrets,
)
from jarvis.core.exceptions import (
    ConfigurationError,
    EnvironmentValidationError,
    EnvironmentSecurityError,
)

__all__ = [
    "Settings",
    "get_settings",
    "AppEnvironment",
    "VarClassification",
    "EnvScope",
    "EnvVarDef",
    "ENV_REGISTRY",
    "validate_environment",
    "get_environment_diagnostics",
    "parse_and_validate_env_file",
    "verify_git_and_file_security",
    "detect_environment_drift",
    "enforce_environment_security",
    "scan_repository_for_secrets",
    "ConfigurationError",
    "EnvironmentValidationError",
    "EnvironmentSecurityError",
]
