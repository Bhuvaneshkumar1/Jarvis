"""
Working Memory Models and Validation Schemas (Batch 25).
Pydantic v2 data models for memory entries, scopes, retrieval filters, and statistics.
"""

import json
import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

from jarvis.core.enums import MemoryScope, SecurityLevel
from jarvis.core.secrets.redaction import SecretRedactor

MAX_MEMORY_CONTENT_BYTES = 64_000  # 64 KB limit per entry
MAX_METADATA_BYTES = 16_000  # 16 KB limit for metadata JSON

_redactor = SecretRedactor()


class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"


class WorkingMemoryEntry(BaseModel):
    """
    Authoritative Working Memory Entry Data Model.
    Supports versioning, scope isolation, privacy classification, and expiration.
    """

    memory_id: str = Field(default_factory=lambda: f"wmem-{uuid.uuid4().hex[:12]}")
    scope: MemoryScope = Field(default=MemoryScope.WORKING)
    owner_id: str = Field(..., min_length=1)
    conversation_id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    agent_id: Optional[str] = Field(default=None)

    content: str = Field(..., min_length=1)
    content_type: str = Field(default="text/plain")
    classification: SecurityLevel = Field(default=SecurityLevel.INTERNAL)
    priority: int = Field(default=5, ge=1, le=10)

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = Field(default=None)
    version: int = Field(default=1, ge=1)
    source: str = Field(default="working_memory")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE)

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("memory_id cannot be empty or whitespace.")
        return v.strip()

    @field_validator("owner_id")
    @classmethod
    def validate_owner_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("owner_id cannot be empty or whitespace.")
        return v.strip()

    @field_validator("content")
    @classmethod
    def validate_and_sanitize_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content cannot be empty or whitespace.")
        if len(v.encode("utf-8")) > MAX_MEMORY_CONTENT_BYTES:
            raise ValueError(f"Memory content exceeds maximum size of {MAX_MEMORY_CONTENT_BYTES} bytes.")
        # Automatically redact secrets before storing
        return _redactor.redact_text(v)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        try:
            raw_json = json.dumps(v)
        except (TypeError, ValueError) as ex:
            raise ValueError(f"Metadata must be strictly JSON-serializable: {ex}")
        if len(raw_json.encode("utf-8")) > MAX_METADATA_BYTES:
            raise ValueError(f"Metadata exceeds maximum allowed size of {MAX_METADATA_BYTES} bytes.")
        return _redactor.redact_dict(v)

    @model_validator(mode="after")
    def validate_timestamps_and_scope(self) -> "WorkingMemoryEntry":
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError(f"expires_at ({self.expires_at}) must be greater than created_at ({self.created_at}).")

        # Validate scope-specific identifier constraints
        if self.scope == MemoryScope.CONVERSATION and not self.conversation_id:
            # Assign owner_id if conversation_id is not explicitly provided
            self.conversation_id = self.owner_id

        if self.scope == MemoryScope.TASK and not self.task_id:
            self.task_id = self.owner_id

        if self.scope == MemoryScope.AGENT and not self.agent_id:
            self.agent_id = self.owner_id

        return self


class MemoryRetrievalFilter(BaseModel):
    """
    Selective Memory Retrieval Query Filter Model.
    """

    scopes: Optional[List[MemoryScope]] = Field(default=None)
    owner_id: str = Field(..., min_length=1)
    conversation_id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    agent_id: Optional[str] = Field(default=None)

    max_classification: SecurityLevel = Field(default=SecurityLevel.RESTRICTED)
    min_priority: int = Field(default=1, ge=1, le=10)
    active_only: bool = Field(default=True)
    exclude_expired: bool = Field(default=True)
    query: Optional[str] = Field(default=None)
    content_type: Optional[str] = Field(default=None)
    limit: int = Field(default=10, ge=1, le=100)
    token_budget: Optional[int] = Field(default=None, ge=1)


class MemoryStatistics(BaseModel):
    """
    Working Memory Usage and Capacity Summary Report.
    """

    total_memories: int = Field(default=0)
    active_memories: int = Field(default=0)
    expired_memories: int = Field(default=0)
    deleted_memories: int = Field(default=0)
    memories_by_scope: Dict[str, int] = Field(default_factory=dict)
    total_content_bytes: int = Field(default=0)
