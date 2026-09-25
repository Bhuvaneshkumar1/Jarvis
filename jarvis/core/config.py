import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

class Settings:
    """
    JARVIS System Configuration loaded from environment / .env.
    Enforces secret discipline (Rule 15) and privacy settings (Rule 14).
    """

    def __init__(self, env_file: Optional[str] = ".env"):
        if env_file and os.path.exists(env_file):
            load_dotenv(dotenv_path=env_file, override=True)
        else:
            load_dotenv()

        self.env: str = os.getenv("JARVIS_ENV", "development")
        self.log_dir: str = os.getenv("JARVIS_LOG_DIR", "logs")
        self.max_memory_mb: int = int(os.getenv("JARVIS_MAX_MEMORY_MB", "8192"))
        self.idle_memory_target_mb: int = int(os.getenv("JARVIS_IDLE_MEMORY_TARGET_MB", "3072"))

        # Security & Policy default toggles
        self.strict_mode: bool = os.getenv("JARVIS_SECURITY_STRICT_MODE", "true").lower() == "true"
        self.allow_auto_create: bool = os.getenv("JARVIS_ALLOW_AUTO_CREATE", "true").lower() == "true"
        self.require_approval_for_modify: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_MODIFY", "true").lower() == "true"
        self.require_approval_for_delete: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_DELETE", "true").lower() == "true"
        self.require_approval_for_git_push: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_GIT_PUSH", "true").lower() == "true"
        self.require_approval_for_financial: bool = os.getenv("JARVIS_REQUIRE_APPROVAL_FOR_FINANCIAL", "true").lower() == "true"

        # Integrations
        self.telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self.obsidian_vault_path: Optional[str] = os.getenv("OBSIDIAN_VAULT_PATH")
        self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
        self.local_llm_url: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")

    def get_redacted_dict(self) -> Dict[str, Any]:
        """Returns configuration dictionary with secrets sanitized."""
        d = self.__dict__.copy()
        for k in ["telegram_bot_token", "openai_api_key", "anthropic_api_key"]:
            if d.get(k):
                d[k] = "[CONFIGURED_SECRET]"
            else:
                d[k] = "[NOT_SET]"
        return d

_global_settings: Optional[Settings] = None

def get_settings(env_file: Optional[str] = ".env", force_reload: bool = False) -> Settings:
    global _global_settings
    if _global_settings is None or force_reload:
        _global_settings = Settings(env_file=env_file)
    return _global_settings
