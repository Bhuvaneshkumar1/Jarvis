"""
HealthStatus Contract Definitions (Section 23).
"""

import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import HealthState


class HealthStatusContract(BaseModel):
    component: str = Field(..., min_length=1)
    status: HealthState = HealthState.HEALTHY
    timestamp: float = Field(default_factory=time.time)
    latency: float = Field(default=0.0, ge=0.0)
    resource_usage: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("component")
    @classmethod
    def validate_component_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("component name cannot be empty or whitespace.")
        return v
