"""
MemoryQuery and MemoryResult Contract Definitions (Section 15 & Section 16).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import MemoryScope

class MemoryQueryContract(BaseModel):
    query: str = Field(..., min_length=1)
    scope: MemoryScope = MemoryScope.WORKING
    project: Optional[str] = None
    task: Optional[str] = None
    user: Optional[str] = None
    limit: int = Field(default=5, ge=1)
    relevance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MemoryResultContract(BaseModel):
    memory_id: str = Field(default_factory=lambda: f"mem-{uuid.uuid4().hex[:12]}")
    content: str = Field(..., min_length=1)
    source: str = Field(default="local_index")
    relevance: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)
    scope: MemoryScope = MemoryScope.WORKING
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("memory_id cannot be empty or whitespace.")
        return v
