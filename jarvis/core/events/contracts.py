"""
Typed Event Contracts and Subscription Definitions for JARVIS Core (Batch 5).
"""

import time
import uuid
from typing import Dict, Any, Optional, List, Callable
from pydantic import BaseModel, Field, ConfigDict, field_validator
from jarvis.core.enums import EventPriority


class Event(BaseModel):
    """
    Base Immutable Event Contract for JARVIS Event Bus.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., min_length=1)
    timestamp: float = Field(default_factory=time.time)
    source: str = Field(default="system")
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: EventPriority = Field(default=EventPriority.NORMAL)
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)

    @field_validator("event_type", "source")
    @classmethod
    def validate_non_empty_str(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace.")
        return v.strip()


class RetryPolicy(BaseModel):
    """
    Configurable Retry Policy for Event Bus Handlers.
    """

    max_attempts: int = Field(default=1, ge=1, le=10)
    retry_delay: float = Field(default=0.0, ge=0.0)
    backoff: float = Field(default=1.0, ge=1.0)
    non_retryable_exceptions: List[str] = Field(
        default_factory=lambda: [
            "ValueError",
            "TypeError",
            "ValidationError",
            "KeyError",
            "PermissionError",
        ]
    )


class Subscription(BaseModel):
    """
    Subscription Contract tracking active Event Bus subscribers.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    subscription_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., min_length=1)
    handler: Callable = Field(...)
    handler_name: str = Field(...)
    is_async: bool = Field(default=True)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout: float = Field(default=5.0, gt=0.0)


# ============================================================================
# SPECIALIZED EVENT CONTRACTS
# ============================================================================


class RuntimeStartingEvent(Event):
    event_type: str = "RuntimeStarting"


class RuntimeStartedEvent(Event):
    event_type: str = "RuntimeStarted"


class RuntimeStoppingEvent(Event):
    event_type: str = "RuntimeStopping"


class RuntimeStoppedEvent(Event):
    event_type: str = "RuntimeStopped"


class RuntimeFailedEvent(Event):
    event_type: str = "RuntimeFailed"


class ComponentRegisteredEvent(Event):
    event_type: str = "ComponentRegistered"


class ComponentInitializingEvent(Event):
    event_type: str = "ComponentInitializing"


class ComponentInitializedEvent(Event):
    event_type: str = "ComponentInitialized"


class ComponentStartedEvent(Event):
    event_type: str = "ComponentStarted"


class ComponentStoppedEvent(Event):
    event_type: str = "ComponentStopped"


class ComponentFailedEvent(Event):
    event_type: str = "ComponentFailed"


class SystemErrorEvent(Event):
    event_type: str = "SystemError"
    priority: EventPriority = EventPriority.CRITICAL


class SystemWarningEvent(Event):
    event_type: str = "SystemWarning"
    priority: EventPriority = EventPriority.HIGH


class SystemHealthChangedEvent(Event):
    event_type: str = "SystemHealthChanged"
