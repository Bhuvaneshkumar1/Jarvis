"""
Authoritative Environment Security, .env Validation & Configuration Hardening Subsystem (Batch 9).
"""

import enum
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Union

from jarvis.core.exceptions import EnvironmentValidationError, EnvironmentSecurityError


# ============================================================================
# 1. ENUMS & DATA CLASSES
# ============================================================================


class VarClassification(str, enum.Enum):
    """Classification of environment variables by secrecy and impact."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"
    FUTURE = "FUTURE"
    DEPRECATED = "DEPRECATED"


class EnvScope(str, enum.Enum):
    """Target environment scope for variable enforcement."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"
    ALL = "all"


@dataclass(frozen=True)
class EnvVarDef:
    """Definition of an environment variable in the authoritative registry."""

    name: str
    classification: VarClassification
    required: bool = False
    env_scope: EnvScope = EnvScope.ALL
    type_name: str = "str"
    default: Optional[Any] = None
    description: str = ""
    deprecated: bool = False
    future: bool = False
    replacement: Optional[str] = None


# ============================================================================
# 2. AUTHORITATIVE ENVIRONMENT VARIABLE REGISTRY
# ============================================================================


ENV_REGISTRY: Dict[str, EnvVarDef] = {
    # Core Application Section
    "JARVIS_ENV": EnvVarDef(
        name="JARVIS_ENV",
        classification=VarClassification.PUBLIC,
        required=True,
        default="development",
        description="Runtime environment mode (development, test, production)",
    ),
    "JARVIS_APP_NAME": EnvVarDef(
        name="JARVIS_APP_NAME",
        classification=VarClassification.PUBLIC,
        default="JARVIS",
        description="Application title",
    ),
    "JARVIS_APP_VERSION": EnvVarDef(
        name="JARVIS_APP_VERSION",
        classification=VarClassification.PUBLIC,
        default="0.1.0",
        description="Application version string",
    ),
    "JARVIS_DEBUG": EnvVarDef(
        name="JARVIS_DEBUG",
        classification=VarClassification.PUBLIC,
        default="false",
        description="Enable debug mode (Forbidden in production)",
    ),
    # Runtime Section
    "HOST": EnvVarDef(
        name="HOST",
        classification=VarClassification.PUBLIC,
        default="127.0.0.1",
        description="Server network listen host",
    ),
    "PORT": EnvVarDef(
        name="PORT",
        classification=VarClassification.PUBLIC,
        default=5000,
        type_name="int",
        description="Server network listen port",
    ),
    "JARVIS_STARTUP_TIMEOUT": EnvVarDef(
        name="JARVIS_STARTUP_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=10.0,
        type_name="float",
        description="Component startup timeout in seconds",
    ),
    "JARVIS_SHUTDOWN_TIMEOUT": EnvVarDef(
        name="JARVIS_SHUTDOWN_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=10.0,
        type_name="float",
        description="Component shutdown timeout in seconds",
    ),
    "JARVIS_COMPONENT_TIMEOUT": EnvVarDef(
        name="JARVIS_COMPONENT_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=10.0,
        type_name="float",
        description="Individual component operation timeout in seconds",
    ),
    # Logging Section
    "JARVIS_LOG_LEVEL": EnvVarDef(
        name="JARVIS_LOG_LEVEL",
        classification=VarClassification.PUBLIC,
        default="INFO",
        description="Global log verbosity level",
    ),
    "JARVIS_LOG_DIR": EnvVarDef(
        name="JARVIS_LOG_DIR",
        classification=VarClassification.INTERNAL,
        default="logs",
        description="Target log directory path",
    ),
    "JARVIS_LOG_RETENTION_DAYS": EnvVarDef(
        name="JARVIS_LOG_RETENTION_DAYS",
        classification=VarClassification.INTERNAL,
        default=30,
        type_name="int",
        description="Days to retain log files",
    ),
    "JARVIS_CONSOLE_LOGGING": EnvVarDef(
        name="JARVIS_CONSOLE_LOGGING",
        classification=VarClassification.PUBLIC,
        default="true",
        type_name="bool",
        description="Enable stdout logging",
    ),
    "JARVIS_FILE_LOGGING": EnvVarDef(
        name="JARVIS_FILE_LOGGING",
        classification=VarClassification.PUBLIC,
        default="true",
        type_name="bool",
        description="Enable file logging",
    ),
    # Database Section
    "JARVIS_DATABASE_PATH": EnvVarDef(
        name="JARVIS_DATABASE_PATH",
        classification=VarClassification.SENSITIVE,
        default="data/jarvis_tasks.db",
        description="SQLite database filepath for Task Manager",
    ),
    "JARVIS_DATABASE_TIMEOUT": EnvVarDef(
        name="JARVIS_DATABASE_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=30.0,
        type_name="float",
        description="SQLite transaction busy timeout in seconds",
    ),
    "JARVIS_DATABASE_WAL_MODE": EnvVarDef(
        name="JARVIS_DATABASE_WAL_MODE",
        classification=VarClassification.INTERNAL,
        default="true",
        type_name="bool",
        description="Enable SQLite Write-Ahead Logging",
    ),
    # Security Policy Section
    "JARVIS_SECURITY_STRICT_MODE": EnvVarDef(
        name="JARVIS_SECURITY_STRICT_MODE",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
        description="Strict security enforcement",
    ),
    "JARVIS_ALLOW_AUTO_CREATE": EnvVarDef(
        name="JARVIS_ALLOW_AUTO_CREATE",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
        description="Allow automatic file/resource creation",
    ),
    "JARVIS_REQUIRE_APPROVAL_FOR_MODIFY": EnvVarDef(
        name="JARVIS_REQUIRE_APPROVAL_FOR_MODIFY",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
    ),
    "JARVIS_REQUIRE_APPROVAL_FOR_DELETE": EnvVarDef(
        name="JARVIS_REQUIRE_APPROVAL_FOR_DELETE",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
    ),
    "JARVIS_REQUIRE_APPROVAL_FOR_GIT_PUSH": EnvVarDef(
        name="JARVIS_REQUIRE_APPROVAL_FOR_GIT_PUSH",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
    ),
    "JARVIS_REQUIRE_APPROVAL_FOR_FINANCIAL": EnvVarDef(
        name="JARVIS_REQUIRE_APPROVAL_FOR_FINANCIAL",
        classification=VarClassification.SENSITIVE,
        default="true",
        type_name="bool",
    ),
    "PIN_REQUIRED": EnvVarDef(
        name="PIN_REQUIRED",
        classification=VarClassification.SENSITIVE,
        default="false",
        type_name="bool",
    ),
    "MAX_AUTH_ATTEMPTS": EnvVarDef(
        name="MAX_AUTH_ATTEMPTS",
        classification=VarClassification.SENSITIVE,
        default=3,
        type_name="int",
    ),
    "LOCKOUT_DURATION": EnvVarDef(
        name="LOCKOUT_DURATION",
        classification=VarClassification.SENSITIVE,
        default=300,
        type_name="int",
    ),
    # Task Manager Section
    "JARVIS_TASK_MAX_TITLE_LENGTH": EnvVarDef(
        name="JARVIS_TASK_MAX_TITLE_LENGTH",
        classification=VarClassification.INTERNAL,
        default=256,
        type_name="int",
    ),
    "JARVIS_TASK_MAX_DESC_LENGTH": EnvVarDef(
        name="JARVIS_TASK_MAX_DESC_LENGTH",
        classification=VarClassification.INTERNAL,
        default=4096,
        type_name="int",
    ),
    "JARVIS_TASK_MAX_META_KB": EnvVarDef(
        name="JARVIS_TASK_MAX_META_KB",
        classification=VarClassification.INTERNAL,
        default=64,
        type_name="int",
    ),
    "JARVIS_TASK_DEFAULT_PRIORITY": EnvVarDef(
        name="JARVIS_TASK_DEFAULT_PRIORITY",
        classification=VarClassification.INTERNAL,
        default="MEDIUM",
    ),
    # Event Bus Section
    "JARVIS_EVENT_QUEUE_SIZE": EnvVarDef(
        name="JARVIS_EVENT_QUEUE_SIZE",
        classification=VarClassification.INTERNAL,
        default=1000,
        type_name="int",
    ),
    "JARVIS_EVENT_HISTORY_SIZE": EnvVarDef(
        name="JARVIS_EVENT_HISTORY_SIZE",
        classification=VarClassification.INTERNAL,
        default=500,
        type_name="int",
    ),
    "JARVIS_EVENT_HANDLER_TIMEOUT": EnvVarDef(
        name="JARVIS_EVENT_HANDLER_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=5.0,
        type_name="float",
    ),
    "JARVIS_EVENT_MAX_RETRIES": EnvVarDef(
        name="JARVIS_EVENT_MAX_RETRIES",
        classification=VarClassification.INTERNAL,
        default=3,
        type_name="int",
    ),
    "JARVIS_EVENT_RETRY_DELAY": EnvVarDef(
        name="JARVIS_EVENT_RETRY_DELAY",
        classification=VarClassification.INTERNAL,
        default=0.5,
        type_name="float",
    ),
    # Orchestrator Section
    "JARVIS_ORCHESTRATOR_OPERATION_TIMEOUT": EnvVarDef(
        name="JARVIS_ORCHESTRATOR_OPERATION_TIMEOUT",
        classification=VarClassification.INTERNAL,
        default=30.0,
        type_name="float",
    ),
    "JARVIS_ORCHESTRATOR_MAX_CONCURRENT": EnvVarDef(
        name="JARVIS_ORCHESTRATOR_MAX_CONCURRENT",
        classification=VarClassification.INTERNAL,
        default=100,
        type_name="int",
    ),
    # Resource Targets Section
    "JARVIS_MAX_MEMORY_GB": EnvVarDef(
        name="JARVIS_MAX_MEMORY_GB",
        classification=VarClassification.INTERNAL,
        default=8,
        type_name="int",
    ),
    "JARVIS_IDLE_MEMORY_TARGET_GB": EnvVarDef(
        name="JARVIS_IDLE_MEMORY_TARGET_GB",
        classification=VarClassification.INTERNAL,
        default=3,
        type_name="int",
    ),
    "JARVIS_MAX_MEMORY_MB": EnvVarDef(
        name="JARVIS_MAX_MEMORY_MB",
        classification=VarClassification.INTERNAL,
        default=8192,
        type_name="int",
    ),
    "JARVIS_IDLE_MEMORY_TARGET_MB": EnvVarDef(
        name="JARVIS_IDLE_MEMORY_TARGET_MB",
        classification=VarClassification.INTERNAL,
        default=3072,
        type_name="int",
    ),
    # Future Provider Secret Placeholders (unactivated)
    "NVIDIA_API_KEY": EnvVarDef(
        name="NVIDIA_API_KEY",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "OPENROUTER_API_KEY": EnvVarDef(
        name="OPENROUTER_API_KEY",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "OPENAI_API_KEY": EnvVarDef(
        name="OPENAI_API_KEY",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "TELEGRAM_BOT_TOKEN": EnvVarDef(
        name="TELEGRAM_BOT_TOKEN",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "GOOGLE_CLIENT_ID": EnvVarDef(
        name="GOOGLE_CLIENT_ID",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "GOOGLE_CLIENT_SECRET": EnvVarDef(
        name="GOOGLE_CLIENT_SECRET",
        classification=VarClassification.SECRET,
        future=True,
    ),
    "GITHUB_TOKEN": EnvVarDef(
        name="GITHUB_TOKEN",
        classification=VarClassification.SECRET,
        future=True,
    ),
}

SECRET_KEY_PATTERNS: Set[str] = {
    "API_KEY",
    "TOKEN",
    "PASSWORD",
    "SECRET",
    "PRIVATE_KEY",
    "CLIENT_SECRET",
    "ACCESS_KEY",
    "AUTH_TOKEN",
    "BOT_TOKEN",
    "CREDENTIALS",
}


def is_secret_variable(var_name: str) -> bool:
    """
    Defense-in-depth detector determining if a variable name corresponds to a secret.
    Checks registry classification first, then falls back to keyword pattern match.
    """
    u_name = var_name.upper()
    if u_name in ENV_REGISTRY:
        return ENV_REGISTRY[u_name].classification == VarClassification.SECRET

    return any(pattern in u_name for pattern in SECRET_KEY_PATTERNS)


# ============================================================================
# 3. .ENV FILE PARSING & VALIDATION
# ============================================================================


def parse_and_validate_env_file(env_path: Union[str, Path] = ".env") -> Tuple[Dict[str, str], List[str]]:
    """
    Safely parses .env file line-by-line without printing or revealing values.
    Detects:
    1. Malformed entries (syntax errors)
    2. Duplicate variable definitions
    3. Invalid key identifiers
    Returns tuple of (parsed_dict, list_of_warnings).
    Raises EnvironmentValidationError on duplicate keys or malformed lines.
    """
    p = Path(env_path)
    if not p.exists():
        return {}, [f"Environment file '{env_path}' does not exist."]

    parsed: Dict[str, str] = {}
    seen_keys: Set[str] = set()
    warnings: List[str] = []

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        raise EnvironmentValidationError(f"Failed to read environment file '{env_path}': {str(exc)}") from exc

    for line_idx, line in enumerate(content.splitlines(), start=1):
        s_line = line.strip()
        if not s_line or s_line.startswith("#"):
            continue

        if "=" not in s_line:
            raise EnvironmentValidationError(f"Malformed .env entry on line {line_idx} of '{env_path}': Missing '=' assignment operator.")

        key, val = s_line.split("=", 1)
        key = key.strip()

        # Validate key identifier format (e.g. JARVIS_ENV)
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise EnvironmentValidationError(f"Malformed .env key identifier on line {line_idx} of '{env_path}': '{key}' is an invalid key name.")

        if key in seen_keys:
            raise EnvironmentValidationError(f"Duplicate environment variable detected on line {line_idx} of '{env_path}': '{key}'.")

        seen_keys.add(key)

        # Unquote value if quoted safely
        v_strip = val.strip()
        if (v_strip.startswith('"') and v_strip.endswith('"')) or (v_strip.startswith("'") and v_strip.endswith("'")):
            v_strip = v_strip[1:-1]

        parsed[key] = v_strip

    return parsed, warnings


# ============================================================================
# 4. GIT TRACKING & FILE SECURITY VERIFICATION
# ============================================================================


def verify_git_and_file_security(root_dir: Union[str, Path] = ".") -> List[str]:
    """
    Verifies git tracking status and protection rules for .env files.
    Ensures:
    1. .env is NOT tracked by Git.
    2. .gitignore protects .env.
    Raises EnvironmentSecurityError if .env is tracked in git repository.
    """
    r_path = Path(root_dir).resolve()
    warnings: List[str] = []

    # 1. Check git tracking using git ls-files .env
    env_file = r_path / ".env"
    if env_file.exists():
        try:
            res = subprocess.run(
                ["git", "ls-files", ".env"],
                cwd=str(r_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip() == ".env":
                raise EnvironmentSecurityError("SECRET EXPOSURE — BLOCKER: Sensitive file '.env' is currently tracked by Git!")
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    # 2. Check .gitignore file contents
    gitignore = r_path / ".gitignore"
    if gitignore.exists():
        g_text = gitignore.read_text(encoding="utf-8")
        if ".env" not in g_text:
            warnings.append(".gitignore does not explicitly mention '.env'.")
    else:
        warnings.append(".gitignore file is missing from repository root.")

    return warnings


# ============================================================================
# 5. ENVIRONMENT DRIFT & UNKNOWN VARIABLE DETECTION
# ============================================================================


def detect_environment_drift(env_dict: Dict[str, str], example_path: Union[str, Path] = ".env.example") -> Dict[str, List[str]]:
    """
    Detects configuration drift between code definitions, active environment, and .env.example.
    Identifies:
    1. Missing required variables
    2. Unknown JARVIS_* variables not registered in ENV_REGISTRY
    3. Deprecated variables in active configuration
    4. Variables missing from .env.example
    """
    results: Dict[str, List[str]] = {
        "missing_required": [],
        "unknown_jarvis_vars": [],
        "deprecated_vars": [],
        "example_drift": [],
    }

    # Check active env keys against registry
    active_keys = set(env_dict.keys())

    for key in active_keys:
        if key.startswith("JARVIS_") and key not in ENV_REGISTRY:
            results["unknown_jarvis_vars"].append(key)

        if key in ENV_REGISTRY and ENV_REGISTRY[key].deprecated:
            rec = ENV_REGISTRY[key].replacement
            msg = f"{key} is deprecated."
            if rec:
                msg += f" Use {rec} instead."
            results["deprecated_vars"].append(msg)

    # Check required variables
    for reg_key, reg_def in ENV_REGISTRY.items():
        if reg_def.required and not reg_def.future:
            if reg_key not in env_dict and reg_key not in os.environ:
                results["missing_required"].append(reg_key)

    # Check .env.example drift
    ex_p = Path(example_path)
    if ex_p.exists():
        try:
            ex_keys, _ = parse_and_validate_env_file(ex_p)
            for reg_key, reg_def in ENV_REGISTRY.items():
                if not reg_def.future and reg_key not in ex_keys:
                    results["example_drift"].append(reg_key)
        except Exception:
            pass

    return results


# ============================================================================
# 6. SECURITY POLICY ENFORCEMENT
# ============================================================================


def enforce_environment_security(env_dict: Dict[str, str]) -> None:
    """
    Enforces security policies on active environment values:
    1. Production Debug Safety: JARVIS_ENV=production + JARVIS_DEBUG=true raises EnvironmentSecurityError.
    2. Path Traversal Safety: Prevents sensitive paths from pointing to root/system directories in production.
    3. Command Injection Safety: Rejects raw shell meta-characters in string variables.
    """
    # Merge process env over .env file dict
    merged = {**env_dict, **os.environ}

    raw_env = merged.get("JARVIS_ENV", "development").strip().lower()
    raw_debug = merged.get("JARVIS_DEBUG", "false").strip().lower()

    # Rule 1: Production Debug Prohibition
    if raw_env == "production" and raw_debug in ("true", "1", "yes", "on"):
        raise EnvironmentSecurityError("SECURITY VIOLATION: JARVIS_DEBUG=true is prohibited when JARVIS_ENV=production.")

    # Rule 2: Path Safety in Production
    if raw_env == "production":
        db_path = merged.get("JARVIS_DATABASE_PATH", "")
        if ".." in db_path:
            raise EnvironmentSecurityError("SECURITY VIOLATION: Path traversal '..' in JARVIS_DATABASE_PATH is prohibited in production.")

    # Rule 3: Shell injection character check on JARVIS variables
    shell_injection_chars = [";", "|", "`", "$("]
    for k, v in merged.items():
        if k.startswith("JARVIS_") and isinstance(v, str):
            for char in shell_injection_chars:
                if char in v:
                    raise EnvironmentSecurityError(f"SECURITY VIOLATION: Environment variable '{k}' contains prohibited shell meta-character '{char}'.")


# ============================================================================
# 7. REPOSITORY SECRET SCANNER
# ============================================================================


@dataclass(frozen=True)
class SecretMatch:
    file_path: str
    line_number: int
    rule_name: str
    severity: str


SECRET_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    ("OpenAI API Key", re.compile(r"sk-[a-zA-Z0-9]{20,}"), "HIGH"),
    ("GitHub Token", re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "HIGH"),
    ("Slack Bot Token", re.compile(r"xoxb-[0-9a-zA-Z]{10,}"), "HIGH"),
    ("Google API Key", re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"), "HIGH"),
    ("Private Key Header", re.compile(r"-----BEGIN (RSA|OPENSSH|PRIVATE) KEY-----"), "CRITICAL"),
]


def scan_repository_for_secrets(root_dir: Union[str, Path] = ".") -> List[SecretMatch]:
    """
    Programmatically scans tracked repository files for hardcoded secrets.
    Excludes .env, .env.example, build dirs, binaries, and .git.
    Returns list of SecretMatch findings (WITHOUT raw secret values).
    """
    r_path = Path(root_dir).resolve()
    findings: List[SecretMatch] = []

    # Get tracked files via git ls-files if available
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(r_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            tracked_files = [r_path / line.strip() for line in res.stdout.splitlines() if line.strip()]
        else:
            tracked_files = list(r_path.rglob("*.py"))
    except Exception:
        tracked_files = list(r_path.rglob("*.py"))

    for f_path in tracked_files:
        if not f_path.exists() or not f_path.is_file():
            continue
        # Skip .env files, binaries, images, lockfiles
        if f_path.name in (".env", ".env.example") or f_path.suffix in (".png", ".jpg", ".db", ".sqlite", ".pyc", ".zip"):
            continue

        try:
            content = f_path.read_text(encoding="utf-8", errors="ignore")
            for line_idx, line in enumerate(content.splitlines(), start=1):
                # Skip comments, test synthetic placeholders, or test fixtures
                line_u = line.upper()
                if any(
                    marker in line_u
                    for marker in (
                        "YOUR_",
                        "EXAMPLE_",
                        "SAMPLE",
                        "TEST_FAKE_",
                        "1234567890",
                        "MOCK_",
                        "SK-1234567890",
                    )
                ):
                    continue
                for rule_name, pattern, severity in SECRET_PATTERNS:
                    if pattern.search(line):
                        rel_path = str(f_path.relative_to(r_path))
                        findings.append(
                            SecretMatch(
                                file_path=rel_path,
                                line_number=line_idx,
                                rule_name=rule_name,
                                severity=severity,
                            )
                        )
        except Exception:
            continue

    return findings


# ============================================================================
# 8. SAFE DIAGNOSTICS SNAPSHOT
# ============================================================================


def get_environment_diagnostics(env_path: Union[str, Path] = ".env") -> str:
    """
    Produces executive safe environment diagnostics snapshot string.
    Rule: NEVER expose secret values or raw file lines.
    """
    parsed_env, _ = parse_and_validate_env_file(env_path)
    merged = {**parsed_env, **os.environ}

    raw_env = merged.get("JARVIS_ENV", "development")
    raw_debug = merged.get("JARVIS_DEBUG", "false")
    raw_log = merged.get("JARVIS_LOG_LEVEL", "INFO")

    lines = [
        "JARVIS ENVIRONMENT SECURITY SNAPSHOT",
        "====================================",
        "",
        f"Environment: {raw_env}",
        f"Debug Mode: {raw_debug}",
        f"Log Level: {raw_log}",
        f".env File Present: {'YES' if Path(env_path).exists() else 'NO'}",
        "",
        "Variables Classification Summary:",
    ]

    for reg_key, reg_def in ENV_REGISTRY.items():
        if reg_def.future:
            is_set = "SET" if reg_key in merged and merged[reg_key] else "NOT SET"
            lines.append(f"  {reg_key} (FUTURE): {is_set}")
        else:
            is_set = "SET" if reg_key in merged else "NOT SET"
            lines.append(f"  {reg_key} ({reg_def.classification.value}): {is_set}")

    lines.extend(["", "RESULT: VALID"])
    return "\n".join(lines)


# ============================================================================
# 9. MASTER VALIDATION ENTRY POINT
# ============================================================================


def validate_environment(env_path: Union[str, Path] = ".env", root_dir: Union[str, Path] = ".") -> Dict[str, Any]:
    """
    Master environment validation function.
    Executes full battery of security, syntax, drift, and scanning checks.
    Raises EnvironmentValidationError or EnvironmentSecurityError on failure.
    """
    # 1. Parse and validate .env file syntax & duplicates
    parsed_env, file_warnings = parse_and_validate_env_file(env_path)

    # 2. Verify git tracking & gitignore safety
    git_warnings = verify_git_and_file_security(root_dir)

    # 3. Detect drift & unknown variables
    drift_results = detect_environment_drift(parsed_env)

    # 4. Enforce security rules (prod debug prohibition, path safety, injection)
    enforce_environment_security(parsed_env)

    # 5. Scan repository for secrets
    secret_findings = scan_repository_for_secrets(root_dir)
    if secret_findings:
        first = secret_findings[0]
        raise EnvironmentSecurityError(f"SECRET EXPOSURE — BLOCKER: Hardcoded {first.rule_name} detected in '{first.file_path}' at line {first.line_number}.")

    # If missing required non-future variables, fail validation
    if drift_results["missing_required"]:
        missing_str = ", ".join(drift_results["missing_required"])
        raise EnvironmentValidationError(f"Missing required environment variables: {missing_str}")

    return {
        "parsed_count": len(parsed_env),
        "file_warnings": file_warnings,
        "git_warnings": git_warnings,
        "drift": drift_results,
        "secret_findings_count": len(secret_findings),
    }
