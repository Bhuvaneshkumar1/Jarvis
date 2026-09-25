"""
Response Contract Definitions (Section 7).
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import ResponseStatus, OutputType


class ResponseContract(BaseModel):
    response_id: str = Field(default_factory=lambda: f"res-{uuid.uuid4().hex[:12]}")
    request_id: str
    status: ResponseStatus = ResponseStatus.SUCCESS
    content: Optional[str] = None
    output_type: OutputType = OutputType.TEXT
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("response_id", "request_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v
