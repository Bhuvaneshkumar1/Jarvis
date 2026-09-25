"""
Request Contract Definitions (Section 6).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import RequestSource, InputType


class RequestContract(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    source: RequestSource = RequestSource.LOCAL_UI
    input_type: InputType = InputType.TEXT
    content: str = Field(..., min_length=1)
    timestamp: float = Field(default_factory=time.time)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty or whitespace.")
        return v
