"""
Core Configuration module re-exporting authoritative Centralized Configuration System (Batch 8).
Prevents duplicate configuration loaders and scattered os.getenv calls across JARVIS.
"""

from config.settings import (
    Settings,
    get_settings,
    AppEnvironment,
)
from jarvis.core.exceptions import ConfigurationError

__all__ = [
    "Settings",
    "get_settings",
    "AppEnvironment",
    "ConfigurationError",
]
