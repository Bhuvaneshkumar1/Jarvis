import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from jarvis.core.exceptions import ConfigurationError

class Settings:
    """
    Provider-neutral typed configuration access foundation (Section 10).
    Loads environment variables from .env and validates system parameters.
    """

    def __init__(self, env_file: Optional[str] = ".env"):
        if env_file and os.path.exists(env_file):
            load_dotenv(dotenv_path=env_file, override=True)
        else:
            load_dotenv()

        # Required System Configuration
        self.env: str = os.getenv("JARVIS_ENV", "development")
        self.log_dir: str = os.getenv("JARVIS_LOG_DIR", "logs")
        self.host: str = os.getenv("HOST", "127.0.0.1")

        try:
            self.port: int = int(os.getenv("PORT", "5000"))
        except ValueError:
            raise ConfigurationError(f"Invalid PORT value in configuration: '{os.getenv('PORT')}' is not an integer.")

        try:
            self.max_memory_mb: int = int(os.getenv("JARVIS_MAX_MEMORY_MB", "8192"))
        except ValueError:
            raise ConfigurationError(f"Invalid JARVIS_MAX_MEMORY_MB value: '{os.getenv('JARVIS_MAX_MEMORY_MB')}' is not an integer.")

        # Security & Policy Default Toggles
        self.strict_mode: bool = os.getenv("JARVIS_SECURITY_STRICT_MODE", "true").lower() == "true"
        self.allow_auto_create: bool = os.getenv("JARVIS_ALLOW_AUTO_CREATE", "true").lower() == "true"
        self.require_approval_for_modify: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_MODIFY", "true").lower() == "true"
        self.require_approval_for_delete: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_DELETE", "true").lower() == "true"

        # Optional Integration Placeholders
        self.telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self.nvidia_api_key: Optional[str] = os.getenv("NVIDIA_API_KEY")
        self.openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")

        self.validate()

    def validate(self):
        """Validates configuration bounds."""
        if self.max_memory_mb < 512:
            raise ConfigurationError(f"JARVIS_MAX_MEMORY_MB ({self.max_memory_mb} MB) is below minimum threshold of 512 MB.")
        if not (1 <= self.port <= 65535):
            raise ConfigurationError(f"PORT ({self.port}) is out of valid range (1-65535).")

    def get_sanitized_summary(self) -> Dict[str, Any]:
        """Returns safe configuration summary without leaking actual secret values."""
        return {
            "env": self.env,
            "log_dir": self.log_dir,
            "host": self.host,
            "port": self.port,
            "max_memory_mb": self.max_memory_mb,
            "strict_mode": self.strict_mode,
            "telegram_bot_configured": bool(self.telegram_bot_token),
            "nvidia_api_configured": bool(self.nvidia_api_key),
            "openrouter_api_configured": bool(self.openrouter_api_key),
            "github_token_configured": bool(self.github_token),
        }

_settings_instance: Optional[Settings] = None

def get_settings(env_file: Optional[str] = ".env", force_reload: bool = False) -> Settings:
    global _settings_instance
    if _settings_instance is None or force_reload:
        _settings_instance = Settings(env_file=env_file)
    return _settings_instance
