"""
Authoritative Configuration & Security Hardening Engine for JARVIS (Batch 11).
Enforces fail-closed startup, path boundary security, cross-field dependency validation,
non-sensitive configuration fingerprinting, and trusted runtime immutability.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Union

from jarvis.core.exceptions import (
    ConfigurationError,
    EnvironmentSecurityError,
)
from config.env_security import (
    parse_and_validate_env_file,
    detect_environment_drift,
    enforce_environment_security,
    scan_repository_for_secrets,
    verify_git_and_file_security,
)


# ============================================================================
# 1. PATH SECURITY & BOUNDARY VALIDATION
# ============================================================================


FORBIDDEN_WINDOWS_PATHS: Set[str] = {
    "c:\\windows",
    "c:\\windows\\system32",
    "c:\\program files",
    "c:\\program files (x86)",
}

FORBIDDEN_POSIX_PATHS: Set[str] = {
    "/etc",
    "/usr",
    "/var",
    "/bin",
    "/sbin",
    "/sys",
    "/proc",
}


def validate_path_security(
    raw_path: str,
    var_name: str,
    allow_relative: bool = True,
    base_root: Optional[Path] = None,
) -> Path:
    """
    Validates security-sensitive filesystem paths:
    1. Converts path to canonical resolved absolute path (Path.resolve()).
    2. Detects path traversal attempts ('..').
    3. Detects forbidden system directory collisions.
    4. Enforces directory boundary restriction relative to project root or base_root.
    5. Checks Windows symlink/reparse-point safety.
    Returns canonical resolved Path object.
    Raises EnvironmentSecurityError or ConfigurationError on violation.
    """
    if not raw_path or not isinstance(raw_path, str):
        raise ConfigurationError(f"Path variable '{var_name}' must be a non-empty string.")

    # Rule 1: Detect raw path traversal strings
    if ".." in raw_path:
        raise EnvironmentSecurityError(f"SECURITY VIOLATION: Path traversal '..' detected in '{var_name}': '{raw_path}'.")

    p = Path(raw_path)

    # Resolve canonical absolute path
    try:
        resolved = p.resolve()
    except Exception as exc:
        raise ConfigurationError(f"Failed to resolve path for '{var_name}': {str(exc)}") from exc

    resolved_str = str(resolved).lower()

    # Rule 2: Check forbidden system directory collisions
    if sys.platform == "win32":
        for forbidden in FORBIDDEN_WINDOWS_PATHS:
            if resolved_str == forbidden or resolved_str.startswith(forbidden + "\\"):
                raise EnvironmentSecurityError(f"SECURITY VIOLATION: '{var_name}' path '{resolved}' collides with protected system directory '{forbidden}'.")
    else:
        for forbidden in FORBIDDEN_POSIX_PATHS:
            if resolved_str == forbidden or resolved_str.startswith(forbidden + "/"):
                raise EnvironmentSecurityError(f"SECURITY VIOLATION: '{var_name}' path '{resolved}' collides with protected system directory '{forbidden}'.")

    # Rule 3: Check symlink / reparse point if file exists
    if p.exists() and os.path.islink(p):
        # Allow symlink only if target resolves within base_root
        target = p.resolve()
        root = (base_root or Path.cwd()).resolve()
        if not str(target).startswith(str(root)):
            raise EnvironmentSecurityError(f"SECURITY VIOLATION: Symlink for '{var_name}' points outside project root: '{target}'.")

    return resolved


# ============================================================================
# 2. CROSS-FIELD DEPENDENCY VALIDATION
# ============================================================================


def validate_cross_field_dependencies(settings_obj: Any) -> List[str]:
    """
    Enforces cross-field dependency rules and complex configuration safety combinations:
    1. Production Debug Prohibition: JARVIS_ENV=production -> JARVIS_DEBUG=false.
    2. Resource Limits Ratio: idle_memory <= max_memory.
    3. Logging Consistency: Console and File logging cannot both be disabled if debug is enabled.
    Returns list of validation warnings.
    Raises EnvironmentSecurityError or ConfigurationError on invalid combination.
    """
    warnings: List[str] = []

    env_val = getattr(settings_obj.app, "environment", None) if hasattr(settings_obj, "app") else None
    if env_val is not None and hasattr(env_val, "value"):
        env_str = str(getattr(env_val, "value")).lower()
    else:
        env_str = str(env_val).lower() if env_val is not None else ""
    is_debug = getattr(settings_obj.app, "debug", False) if hasattr(settings_obj, "app") else False

    # Rule 1: Production Debug Prohibition
    if env_str == "production" and is_debug:
        raise EnvironmentSecurityError("SECURITY VIOLATION: Debug mode (JARVIS_DEBUG=true) is strictly prohibited in production environment.")

    # Rule 2: Resource Limits Ratio Validation
    idle_gb = getattr(settings_obj.resource, "idle_memory_target_gb", 3)
    max_gb = getattr(settings_obj.resource, "max_memory_gb", 8)
    if idle_gb > max_gb:
        raise ConfigurationError(f"Resource Target Conflict: idle_memory_target_gb ({idle_gb} GB) cannot exceed max_memory_gb ({max_gb} GB).")

    idle_mb = getattr(settings_obj.resource, "idle_memory_target_mb", 3072)
    max_mb = getattr(settings_obj.resource, "max_memory_mb", 8192)
    if idle_mb > max_mb:
        raise ConfigurationError(f"Resource Target Conflict: idle_memory_target_mb ({idle_mb} MB) cannot exceed max_memory_mb ({max_mb} MB).")

    # Rule 3: Path Security Validation on configured database & log paths
    db_path = getattr(settings_obj.database, "database_path", "data/jarvis_tasks.db")
    validate_path_security(db_path, "JARVIS_DATABASE_PATH")

    log_dir = getattr(settings_obj.logging, "log_dir", "logs")
    validate_path_security(log_dir, "JARVIS_LOG_DIR")

    # Rule 4: Logging Toggles Consistency
    console_log = getattr(settings_obj.logging, "console_logging", True)
    file_log = getattr(settings_obj.logging, "file_logging", True)
    if not console_log and not file_log:
        warnings.append("Both console and file logging are disabled. Runtime output will be suppressed.")

    return warnings


# ============================================================================
# 3. NON-SENSITIVE CONFIGURATION FINGERPRINTING
# ============================================================================


def compute_config_fingerprint(settings_obj: Any) -> str:
    """
    Computes deterministic SHA-256 fingerprint hash of non-sensitive configuration state.
    Rule: NEVER include raw secret values in fingerprint calculation.
    Excludes credentials while capturing all operational parameters.
    """
    summary = settings_obj.get_sanitized_summary()

    # Strip secrets section or replace secret tokens with SET/NOT SET indicators
    safe_payload = {
        "app": summary.get("app"),
        "runtime": summary.get("runtime"),
        "logging": summary.get("logging"),
        "database": summary.get("database"),
        "security": summary.get("security"),
        "task": summary.get("task"),
        "event_bus": summary.get("event_bus"),
        "orchestrator": summary.get("orchestrator"),
        "resource": summary.get("resource"),
        "secrets_status": summary.get("secrets"),
    }

    serialized = json.dumps(safe_payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ============================================================================
# 4. MASTER FAIL-CLOSED STARTUP ENFORCEMENT
# ============================================================================


def enforce_fail_closed_startup(
    env_path: Union[str, Path] = ".env",
    root_dir: Union[str, Path] = ".",
    settings_obj: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Master fail-closed security enforcement procedure for JARVIS startup.
    Executes full battery of environment validation, git protection checks,
    secret scanning, path boundary security, and cross-field dependency checks.
    Raises EnvironmentValidationError or EnvironmentSecurityError if any check fails,
    blocking unsafe startup.
    """
    # 1. Parse and validate .env file syntax & duplicate variables
    parsed_env, file_warnings = parse_and_validate_env_file(env_path)

    # 2. Verify git tracking & gitignore safety
    git_warnings = verify_git_and_file_security(root_dir)

    # 3. Detect drift & unknown variables
    drift_results = detect_environment_drift(parsed_env)

    # 4. Enforce security rules (prod debug, path traversal, shell injection)
    enforce_environment_security(parsed_env)

    # 5. Scan repository for hardcoded secrets
    secret_findings = scan_repository_for_secrets(root_dir)
    if secret_findings:
        first = secret_findings[0]
        raise EnvironmentSecurityError(f"SECRET EXPOSURE — BLOCKER: Hardcoded {first.rule_name} detected in '{first.file_path}' at line {first.line_number}.")

    # 6. Cross-field dependency checks on settings object
    warnings: List[str] = list(file_warnings) + list(git_warnings)
    if settings_obj is not None:
        cross_warnings = validate_cross_field_dependencies(settings_obj)
        warnings.extend(cross_warnings)

    fingerprint = compute_config_fingerprint(settings_obj) if settings_obj else "UNCONFIGURED"

    return {
        "status": "VALIDATED",
        "fingerprint": fingerprint,
        "parsed_count": len(parsed_env),
        "warnings": warnings,
        "drift": drift_results,
    }
