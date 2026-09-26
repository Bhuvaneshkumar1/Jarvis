"""
Authoritative Centralized Configuration Management System for JARVIS (Batch 8).
"""

import enum
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from dotenv import dotenv_values
from jarvis.core.enums import TaskPriority
from jarvis.core.exceptions import ConfigurationError


class AppEnvironment(str, enum.Enum):
    """Controlled Application Runtime Environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


def parse_bool(val: Any, var_name: str = "Boolean Variable") -> bool:
    """
    Deterministic boolean parser.
    Accepts: true/false, 1/0, yes/no, on/off (case-insensitive).
    Raises ConfigurationError for invalid or ambiguous values.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val == 1:
            return True
        if val == 0:
            return False
        raise ConfigurationError(f"{var_name} numeric value must be 1 or 0, got '{val}'.")

    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "t", "1", "yes", "y", "on"):
            return True
        if s in ("false", "f", "0", "no", "n", "off"):
            return False
        raise ConfigurationError(f"Invalid boolean value for {var_name}: '{val}'. Expected one of 'true', 'false', '1', '0', 'yes', 'no', 'on', 'off'.")

    raise ConfigurationError(f"Invalid boolean type for {var_name}: '{type(val).__name__}'.")


def parse_int(
    val: Any,
    var_name: str,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
    """
    Parses integer value and validates range.
    Raises ConfigurationError on invalid format or range violation.
    """
    try:
        if isinstance(val, str):
            res = int(val.strip())
        else:
            res = int(val)
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(f"Invalid integer value for {var_name}: '{val}'. Must be an integer.") from exc

    if min_val is not None and res < min_val:
        raise ConfigurationError(f"{var_name} ({res}) is below minimum threshold of {min_val}.")
    if max_val is not None and res > max_val:
        raise ConfigurationError(f"{var_name} ({res}) exceeds maximum allowed limit of {max_val}.")
    return res


def parse_float(
    val: Any,
    var_name: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    """
    Parses float value and validates range.
    Raises ConfigurationError on invalid format or range violation.
    """
    try:
        if isinstance(val, str):
            res = float(val.strip())
        else:
            res = float(val)
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(f"Invalid float value for {var_name}: '{val}'. Must be a number.") from exc

    if min_val is not None and res < min_val:
        raise ConfigurationError(f"{var_name} ({res}) is below minimum threshold of {min_val}.")
    if max_val is not None and res > max_val:
        raise ConfigurationError(f"{var_name} ({res}) exceeds maximum allowed limit of {max_val}.")
    return res


# ============================================================================
# TYPED CONFIGURATION SECTION MODELS
# ============================================================================


class ApplicationConfig(BaseModel):
    """Core Application Settings Section."""

    model_config = ConfigDict(frozen=True)

    environment: AppEnvironment = Field(default=AppEnvironment.DEVELOPMENT)
    application_name: str = Field(default="JARVIS")
    application_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)


class RuntimeConfig(BaseModel):
    """Runtime Lifecycle & Network Settings Section."""

    model_config = ConfigDict(frozen=True)

    startup_timeout: float = Field(default=10.0, gt=0.0, le=300.0)
    shutdown_timeout: float = Field(default=10.0, gt=0.0, le=300.0)
    component_timeout: float = Field(default=10.0, gt=0.0, le=300.0)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    """Logging Subsystem Settings Section."""

    model_config = ConfigDict(frozen=True)

    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="logs")
    log_retention_days: int = Field(default=30, ge=1, le=3650)
    console_logging: bool = Field(default=True)
    file_logging: bool = Field(default=True)


class DatabaseConfig(BaseModel):
    """Task Manager SQLite Database Settings Section."""

    model_config = ConfigDict(frozen=True)

    database_path: str = Field(default="data/jarvis_tasks.db")
    database_timeout: float = Field(default=30.0, gt=0.0)
    database_wal_mode: bool = Field(default=True)


class SecurityConfig(BaseModel):
    """Security Policy & Governance Settings Section."""

    model_config = ConfigDict(frozen=True)

    strict_mode: bool = Field(default=True)
    allow_auto_create: bool = Field(default=True)
    require_approval_for_modify: bool = Field(default=True)
    require_approval_for_delete: bool = Field(default=True)
    require_approval_for_git_push: bool = Field(default=True)
    require_approval_for_financial: bool = Field(default=True)
    pin_required: bool = Field(default=False)
    max_auth_attempts: int = Field(default=3, ge=1)
    lockout_duration_seconds: int = Field(default=300, ge=1)


class TaskConfig(BaseModel):
    """Task Manager Limits & Defaults Settings Section."""

    model_config = ConfigDict(frozen=True)

    max_title_length: int = Field(default=256, ge=1, le=1024)
    max_description_length: int = Field(default=4096, ge=1, le=65536)
    max_metadata_size_kb: int = Field(default=64, ge=1, le=1024)
    default_priority: TaskPriority = Field(default=TaskPriority.MEDIUM)


class EventBusConfig(BaseModel):
    """Internal Event Bus Infrastructure Settings Section."""

    model_config = ConfigDict(frozen=True)

    event_queue_size: int = Field(default=1000, ge=10, le=100000)
    event_history_size: int = Field(default=500, ge=0, le=10000)
    handler_timeout: float = Field(default=5.0, gt=0.0)
    max_handler_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=0.5, ge=0.0)


class OrchestratorConfig(BaseModel):
    """Core Orchestrator Operation Settings Section."""

    model_config = ConfigDict(frozen=True)

    operation_timeout: float = Field(default=30.0, gt=0.0)
    max_concurrent_operations: int = Field(default=100, ge=1, le=10000)


class ResourceConfig(BaseModel):
    """Target Hardware & Resource Limit Settings Section."""

    model_config = ConfigDict(frozen=True)

    max_memory_gb: int = Field(default=8, ge=1, le=1024)
    idle_memory_target_gb: int = Field(default=3, ge=1, le=1024)
    max_memory_mb: int = Field(default=8192, ge=1024)
    idle_memory_target_mb: int = Field(default=3072, ge=512)


class SecretsConfig(BaseModel):
    """Reserved Future Credential Metadata Tracker (No integrations activated)."""

    model_config = ConfigDict(frozen=True)

    nvidia_api_key: Optional[str] = Field(default=None)
    openrouter_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    telegram_bot_token: Optional[str] = Field(default=None)
    google_client_id: Optional[str] = Field(default=None)
    google_client_secret: Optional[str] = Field(default=None)
    github_token: Optional[str] = Field(default=None)


# ============================================================================
# AUTHORITATIVE SETTINGS CONTAINER
# ============================================================================


class Settings:
    """
    Authoritative Immutable Centralized Configuration Container for JARVIS Core.
    Loads and merges defaults, .env file, process environment, and explicit overrides.
    """

    def __init__(
        self,
        env_file: Optional[str] = ".env",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> None:

        merged: Dict[str, Any] = {}

        # 1. Read .env file if present
        if env_file and os.path.exists(env_file):
            try:
                env_file_vals = dotenv_values(dotenv_path=env_file)
                for k, v in env_file_vals.items():
                    if v is not None:
                        merged[k] = v
            except Exception as exc:
                raise ConfigurationError(f"Failed to parse .env configuration file '{env_file}': {str(exc)}") from exc

        # 2. Merge process environment (overrides .env)
        for k, v in os.environ.items():
            merged[k] = v

        # 3. Merge explicit runtime overrides (highest priority)
        if overrides:
            for k, v in overrides.items():
                if v is not None:
                    merged[k] = v

        # --------------------------------------------------------------------
        # Parse & Validate Sections
        # --------------------------------------------------------------------

        # Application Section
        env_raw = merged.get("JARVIS_ENV", "development").strip().lower()
        try:
            env_enum = AppEnvironment(env_raw)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid JARVIS_ENV value: '{env_raw}'. Must be one of 'development', 'test', 'production'.") from exc

        app_name = merged.get("JARVIS_APP_NAME", "JARVIS")
        app_ver = merged.get("JARVIS_APP_VERSION", "0.1.0")
        debug_val = parse_bool(merged.get("JARVIS_DEBUG", "false"), "JARVIS_DEBUG")

        self.app = ApplicationConfig(
            environment=env_enum,
            application_name=app_name,
            application_version=app_ver,
            debug=debug_val,
        )

        # Runtime Section
        host_val = merged.get("HOST", "127.0.0.1")
        port_val = parse_int(merged.get("PORT", 5000), "PORT", min_val=1, max_val=65535)
        startup_to = parse_float(merged.get("JARVIS_STARTUP_TIMEOUT", 10.0), "JARVIS_STARTUP_TIMEOUT", min_val=0.1)
        shutdown_to = parse_float(merged.get("JARVIS_SHUTDOWN_TIMEOUT", 10.0), "JARVIS_SHUTDOWN_TIMEOUT", min_val=0.1)
        comp_to = parse_float(merged.get("JARVIS_COMPONENT_TIMEOUT", 10.0), "JARVIS_COMPONENT_TIMEOUT", min_val=0.1)

        self.runtime = RuntimeConfig(
            startup_timeout=startup_to,
            shutdown_timeout=shutdown_to,
            component_timeout=comp_to,
            host=host_val,
            port=port_val,
        )

        # Logging Section
        log_lvl = merged.get("JARVIS_LOG_LEVEL", "INFO").strip().upper()
        if log_lvl not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ConfigurationError(f"Invalid JARVIS_LOG_LEVEL: '{log_lvl}'. Must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")

        log_dir_val = merged.get("JARVIS_LOG_DIR", "logs")
        log_ret_val = parse_int(merged.get("JARVIS_LOG_RETENTION_DAYS", 30), "JARVIS_LOG_RETENTION_DAYS", min_val=1, max_val=3650)
        console_log = parse_bool(merged.get("JARVIS_CONSOLE_LOGGING", "true"), "JARVIS_CONSOLE_LOGGING")
        file_log = parse_bool(merged.get("JARVIS_FILE_LOGGING", "true"), "JARVIS_FILE_LOGGING")

        self.logging = LoggingConfig(
            log_level=log_lvl,
            log_dir=log_dir_val,
            log_retention_days=log_ret_val,
            console_logging=console_log,
            file_logging=file_log,
        )

        # Database Section
        db_path = merged.get("JARVIS_DATABASE_PATH", merged.get("DATABASE_PATH", "data/jarvis_tasks.db"))
        db_timeout = parse_float(merged.get("JARVIS_DATABASE_TIMEOUT", 30.0), "JARVIS_DATABASE_TIMEOUT", min_val=0.1)
        db_wal = parse_bool(merged.get("JARVIS_DATABASE_WAL_MODE", "true"), "JARVIS_DATABASE_WAL_MODE")

        self.database = DatabaseConfig(
            database_path=db_path,
            database_timeout=db_timeout,
            database_wal_mode=db_wal,
        )

        # Resource Section
        max_mem_mb = parse_int(merged.get("JARVIS_MAX_MEMORY_MB", 8192), "JARVIS_MAX_MEMORY_MB", min_val=512, max_val=1048576)
        idle_mem_mb = parse_int(merged.get("JARVIS_IDLE_MEMORY_TARGET_MB", 3072), "JARVIS_IDLE_MEMORY_TARGET_MB", min_val=256, max_val=1048576)
        max_mem_gb = parse_int(merged.get("JARVIS_MAX_MEMORY_GB", max_mem_mb // 1024 or 8), "JARVIS_MAX_MEMORY_GB", min_val=1, max_val=1024)
        idle_mem_gb = parse_int(merged.get("JARVIS_IDLE_MEMORY_TARGET_GB", idle_mem_mb // 1024 or 3), "JARVIS_IDLE_MEMORY_TARGET_GB", min_val=1, max_val=1024)

        if idle_mem_gb > max_mem_gb:
            raise ConfigurationError(f"JARVIS_IDLE_MEMORY_TARGET_GB ({idle_mem_gb} GB) cannot exceed JARVIS_MAX_MEMORY_GB ({max_mem_gb} GB).")

        self.resource = ResourceConfig(
            max_memory_gb=max_mem_gb,
            idle_memory_target_gb=idle_mem_gb,
            max_memory_mb=max_mem_mb,
            idle_memory_target_mb=idle_mem_mb,
        )

        # Security Section
        strict = parse_bool(merged.get("JARVIS_SECURITY_STRICT_MODE", "true"), "JARVIS_SECURITY_STRICT_MODE")
        auto_create = parse_bool(merged.get("JARVIS_ALLOW_AUTO_CREATE", "true"), "JARVIS_ALLOW_AUTO_CREATE")
        req_modify = parse_bool(merged.get("JARVIS_REQUIRE_APPROVAL_FOR_MODIFY", "true"), "JARVIS_REQUIRE_APPROVAL_FOR_MODIFY")
        req_delete = parse_bool(merged.get("JARVIS_REQUIRE_APPROVAL_FOR_DELETE", "true"), "JARVIS_REQUIRE_APPROVAL_FOR_DELETE")
        req_git = parse_bool(merged.get("JARVIS_REQUIRE_APPROVAL_FOR_GIT_PUSH", "true"), "JARVIS_REQUIRE_APPROVAL_FOR_GIT_PUSH")
        req_fin = parse_bool(merged.get("JARVIS_REQUIRE_APPROVAL_FOR_FINANCIAL", "true"), "JARVIS_REQUIRE_APPROVAL_FOR_FINANCIAL")
        pin_req = parse_bool(merged.get("PIN_REQUIRED", "false"), "PIN_REQUIRED")
        max_auth = parse_int(merged.get("MAX_AUTH_ATTEMPTS", 3), "MAX_AUTH_ATTEMPTS", min_val=1, max_val=100)
        lockout = parse_int(merged.get("LOCKOUT_DURATION", 300), "LOCKOUT_DURATION", min_val=1, max_val=86400)

        self.security = SecurityConfig(
            strict_mode=strict,
            allow_auto_create=auto_create,
            require_approval_for_modify=req_modify,
            require_approval_for_delete=req_delete,
            require_approval_for_git_push=req_git,
            require_approval_for_financial=req_fin,
            pin_required=pin_req,
            max_auth_attempts=max_auth,
            lockout_duration_seconds=lockout,
        )

        # Task Section
        max_t_len = parse_int(merged.get("JARVIS_TASK_MAX_TITLE_LENGTH", 256), "JARVIS_TASK_MAX_TITLE_LENGTH", min_val=10, max_val=1024)
        max_d_len = parse_int(merged.get("JARVIS_TASK_MAX_DESC_LENGTH", 4096), "JARVIS_TASK_MAX_DESC_LENGTH", min_val=100, max_val=65536)
        max_m_kb = parse_int(merged.get("JARVIS_TASK_MAX_META_KB", 64), "JARVIS_TASK_MAX_META_KB", min_val=1, max_val=1024)

        raw_prio = merged.get("JARVIS_TASK_DEFAULT_PRIORITY", "MEDIUM").strip().upper()
        try:
            def_prio = TaskPriority(raw_prio)
        except ValueError:
            def_prio = TaskPriority.MEDIUM

        self.task = TaskConfig(
            max_title_length=max_t_len,
            max_description_length=max_d_len,
            max_metadata_size_kb=max_m_kb,
            default_priority=def_prio,
        )

        # Event Bus Section
        q_size = parse_int(merged.get("JARVIS_EVENT_QUEUE_SIZE", 1000), "JARVIS_EVENT_QUEUE_SIZE", min_val=10, max_val=100000)
        h_size = parse_int(merged.get("JARVIS_EVENT_HISTORY_SIZE", 500), "JARVIS_EVENT_HISTORY_SIZE", min_val=0, max_val=10000)
        h_timeout = parse_float(merged.get("JARVIS_EVENT_HANDLER_TIMEOUT", 5.0), "JARVIS_EVENT_HANDLER_TIMEOUT", min_val=0.1)
        h_retries = parse_int(merged.get("JARVIS_EVENT_MAX_RETRIES", 3), "JARVIS_EVENT_MAX_RETRIES", min_val=0, max_val=10)
        r_delay = parse_float(merged.get("JARVIS_EVENT_RETRY_DELAY", 0.5), "JARVIS_EVENT_RETRY_DELAY", min_val=0.0)

        self.event_bus = EventBusConfig(
            event_queue_size=q_size,
            event_history_size=h_size,
            handler_timeout=h_timeout,
            max_handler_retries=h_retries,
            retry_delay=r_delay,
        )

        # Orchestrator Section
        op_timeout = parse_float(merged.get("JARVIS_ORCHESTRATOR_OPERATION_TIMEOUT", 30.0), "JARVIS_ORCHESTRATOR_OPERATION_TIMEOUT", min_val=0.1)
        max_concurrent = parse_int(merged.get("JARVIS_ORCHESTRATOR_MAX_CONCURRENT", 100), "JARVIS_ORCHESTRATOR_MAX_CONCURRENT", min_val=1, max_val=10000)

        self.orchestrator = OrchestratorConfig(
            operation_timeout=op_timeout,
            max_concurrent_operations=max_concurrent,
        )

        # Secrets Metadata Tracker Section
        self.secrets = SecretsConfig(
            nvidia_api_key=merged.get("NVIDIA_API_KEY"),
            openrouter_api_key=merged.get("OPENROUTER_API_KEY"),
            openai_api_key=merged.get("OPENAI_API_KEY"),
            telegram_bot_token=merged.get("TELEGRAM_BOT_TOKEN"),
            google_client_id=merged.get("GOOGLE_CLIENT_ID"),
            google_client_secret=merged.get("GOOGLE_CLIENT_SECRET"),
            github_token=merged.get("GITHUB_TOKEN"),
        )

        # Freeze instance immutability flag
        self._frozen = True

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise ConfigurationError(f"Settings object is immutable. Cannot set attribute '{name}'.")
        super().__setattr__(name, value)

    # ------------------------------------------------------------------------
    # Flat Compatibility Properties (Preserves existing codebase calls)
    # ------------------------------------------------------------------------

    @property
    def env(self) -> str:
        return self.app.environment.value

    @property
    def log_dir(self) -> str:
        return self.logging.log_dir

    @property
    def host(self) -> str:
        return self.runtime.host

    @property
    def port(self) -> int:
        return self.runtime.port

    @property
    def max_memory_mb(self) -> int:
        return self.resource.max_memory_mb

    @property
    def idle_memory_target_mb(self) -> int:
        return self.resource.idle_memory_target_mb

    @property
    def strict_mode(self) -> bool:
        return self.security.strict_mode

    @property
    def allow_auto_create(self) -> bool:
        return self.security.allow_auto_create

    @property
    def require_approval_for_modify(self) -> bool:
        return self.security.require_approval_for_modify

    @property
    def require_approval_for_delete(self) -> bool:
        return self.security.require_approval_for_delete

    @property
    def require_approval_for_git_push(self) -> bool:
        return self.security.require_approval_for_git_push

    @property
    def require_approval_for_financial(self) -> bool:
        return self.security.require_approval_for_financial

    @property
    def telegram_bot_token(self) -> Optional[str]:
        return self.secrets.telegram_bot_token

    @property
    def nvidia_api_key(self) -> Optional[str]:
        return self.secrets.nvidia_api_key

    @property
    def openrouter_api_key(self) -> Optional[str]:
        return self.secrets.openrouter_api_key

    @property
    def github_token(self) -> Optional[str]:
        return self.secrets.github_token

    @property
    def openai_api_key(self) -> Optional[str]:
        return self.secrets.openai_api_key

    @property
    def local_llm_url(self) -> str:
        return "http://localhost:11434"

    def get_redacted_dict(self) -> Dict[str, Any]:
        """Backward-compatible redacted dictionary representation for privacy tests."""
        return {
            "telegram_bot_token": "[CONFIGURED_SECRET]" if self.secrets.telegram_bot_token else "[NOT_SET]",
            "openai_api_key": "[CONFIGURED_SECRET]" if self.secrets.openai_api_key else "[NOT_SET]",
            "nvidia_api_key": "[CONFIGURED_SECRET]" if self.secrets.nvidia_api_key else "[NOT_SET]",
            "openrouter_api_key": "[CONFIGURED_SECRET]" if self.secrets.openrouter_api_key else "[NOT_SET]",
            "github_token": "[CONFIGURED_SECRET]" if self.secrets.github_token else "[NOT_SET]",
            "env": self.env,
            "log_dir": self.log_dir,
            "max_memory_mb": self.max_memory_mb,
            "idle_memory_target_mb": self.idle_memory_target_mb,
            "strict_mode": self.strict_mode,
        }

    # ------------------------------------------------------------------------
    # Diagnostics and Redaction
    # ------------------------------------------------------------------------

    def get_sanitized_summary(self) -> Dict[str, Any]:
        """
        Returns safe configuration summary without leaking secret values.
        Every credential field is reported ONLY as 'SET' or 'NOT SET'.
        """
        return {
            "app": self.app.model_dump(),
            "runtime": self.runtime.model_dump(),
            "logging": self.logging.model_dump(),
            "database": self.database.model_dump(),
            "security": self.security.model_dump(),
            "task": {
                **self.task.model_dump(),
                "default_priority": self.task.default_priority.value,
            },
            "event_bus": self.event_bus.model_dump(),
            "orchestrator": self.orchestrator.model_dump(),
            "resource": self.resource.model_dump(),
            "secrets": {
                "NVIDIA_API_KEY": "SET" if self.secrets.nvidia_api_key else "NOT SET",
                "OPENROUTER_API_KEY": "SET" if self.secrets.openrouter_api_key else "NOT SET",
                "OPENAI_API_KEY": "SET" if self.secrets.openai_api_key else "NOT SET",
                "TELEGRAM_BOT_TOKEN": "SET" if self.secrets.telegram_bot_token else "NOT SET",
                "GOOGLE_CLIENT_ID": "SET" if self.secrets.google_client_id else "NOT SET",
                "GOOGLE_CLIENT_SECRET": "SET" if self.secrets.google_client_secret else "NOT SET",
                "GITHUB_TOKEN": "SET" if self.secrets.github_token else "NOT SET",
            },
        }

    def get_diagnostics_snapshot(self) -> str:
        """
        Produces formatted executive configuration snapshot string.
        Rule: NEVER expose secret values or structural patterns.
        """
        summary = self.get_sanitized_summary()
        lines = [
            "JARVIS CONFIGURATION",
            "====================",
            "",
            f"Environment: {self.app.environment.value}",
            f"Application: {self.app.application_name} v{self.app.application_version}",
            f"Debug: {str(self.app.debug).lower()}",
            f"Log Level: {self.logging.log_level}",
            "",
            "Database:",
            f"  path: {self.database.database_path}",
            "  configured: YES",
            "",
            "Event Bus:",
            f"  queue size: {self.event_bus.event_queue_size}",
            f"  history size: {self.event_bus.event_history_size}",
            f"  handler timeout: {self.event_bus.handler_timeout}s",
            "",
            "Task Manager:",
            f"  default priority: {self.task.default_priority.value}",
            "",
            "Resources:",
            f"  configured max memory: {self.resource.max_memory_gb} GB",
            "",
            "Secrets:",
        ]

        for sec_key, sec_val in summary["secrets"].items():
            lines.append(f"  {sec_key}: {sec_val}")

        lines.extend(["", "RESULT: VALID"])
        return "\n".join(lines)


# ============================================================================
# SINGLETON INSTANCE LOADER
# ============================================================================

_settings_instance: Optional[Settings] = None


def get_settings(
    env_file: Optional[str] = ".env",
    force_reload: bool = False,
    overrides: Optional[Dict[str, Any]] = None,
) -> Settings:
    """
    Authoritative Settings loader function.
    Returns cached immutable Settings instance unless force_reload=True or overrides are passed.
    """
    global _settings_instance
    if _settings_instance is None or force_reload or overrides is not None:
        _settings_instance = Settings(env_file=env_file, overrides=overrides)
    return _settings_instance
