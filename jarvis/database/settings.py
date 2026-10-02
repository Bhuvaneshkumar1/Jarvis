"""
Typed Database Configuration for JARVIS (Batch 16).
"""

import os
from typing import Optional
from pydantic import BaseModel, Field
from jarvis.core.config import get_settings


class DatabaseSettings(BaseModel):
    db_path: str = Field(default="data/jarvis.db")
    backup_dir: str = Field(default="backups")
    connection_timeout: float = Field(default=30.0, gt=0)
    busy_timeout_ms: int = Field(default=5000, gt=0)
    journal_mode: str = Field(default="WAL")
    synchronous: str = Field(default="NORMAL")
    foreign_keys: bool = Field(default=True)
    auto_migrate: bool = Field(default=True)
    integrity_check_on_startup: bool = Field(default=True)

    def resolve_db_path(self) -> str:
        """Resolve absolute normalized path for database file."""
        return os.path.realpath(os.path.expanduser(os.path.expandvars(self.db_path)))

    def resolve_backup_dir(self) -> str:
        """Resolve absolute normalized path for backup directory."""
        return os.path.realpath(os.path.expanduser(os.path.expandvars(self.backup_dir)))


def get_database_settings(custom_path: Optional[str] = None) -> DatabaseSettings:
    """Load DatabaseSettings from central settings or environment overrides."""
    base_settings = get_settings()
    db_path_val = str(custom_path or getattr(base_settings, "database_path", None) or os.getenv("JARVIS_DATABASE_PATH", "data/jarvis.db"))
    backup_dir_val = str(getattr(base_settings, "database_backup_dir", None) or os.getenv("JARVIS_BACKUP_DIR", "backups"))

    return DatabaseSettings(
        db_path=db_path_val,
        backup_dir=backup_dir_val,
    )
