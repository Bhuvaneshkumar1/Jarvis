"""
Integration Contract Definitions (Section 22).
"""

import uuid
from typing import Dict, Any
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import IntegrationStatus

class IntegrationContract(BaseModel):
    integration_id: str = Field(default_factory=lambda: f"integ-{uuid.uuid4().hex[:12]}")
    provider: str = Field(..., min_length=1)
    capability: str = Field(..., min_length=1)
    status: IntegrationStatus = IntegrationStatus.DISCONNECTED
    authentication_state: str = Field(default="UNAUTHENTICATED")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("integration_id", "provider", "capability")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("String field cannot be empty or whitespace.")
        return v
