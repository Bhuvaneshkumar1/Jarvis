"""
Runtime Context Definition for JARVIS Application Kernel.
"""

import asyncio
import time
import uuid
from typing import Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from config.settings import Settings, get_settings
from jarvis.core.logging import JarvisLogger


class RuntimeContext(BaseModel):
    """
    Controlled shared runtime context for application-level state.
    Passed to components during initialization.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    startup_timestamp: float = Field(default_factory=time.time)
    settings: Settings = Field(default_factory=get_settings)
    logger: JarvisLogger = Field(default_factory=lambda: JarvisLogger(component="Runtime"))
    cancellation_event: asyncio.Event = Field(default_factory=asyncio.Event)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_cancelled(self) -> bool:
        """Check if runtime cancellation has been requested."""
        return self.cancellation_event.is_set()

    def get_uptime(self) -> float:
        """Return runtime uptime in seconds."""
        return max(0.0, time.time() - self.startup_timestamp)
