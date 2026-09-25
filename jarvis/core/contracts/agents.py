"""
Agent and AgentContext Contract Definitions (Section 10 & Section 11).
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import AgentStatus, MemoryScope


class AgentContract(BaseModel):
    agent_id: str = Field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:12]}")
    parent_agent_id: Optional[str] = None
    task_id: str
    role: str = Field(..., min_length=1)
    status: AgentStatus = AgentStatus.CREATED
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    permissions: List[str] = Field(default_factory=list)
    resource_limits: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id", "task_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v


class AgentContextContract(BaseModel):
    agent_id: str
    task_id: str
    parent_task_id: Optional[str] = None
    role: str = Field(..., min_length=1)
    allowed_tools: List[str] = Field(default_factory=list)
    allowed_paths: List[str] = Field(default_factory=list)
    allowed_integrations: List[str] = Field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.WORKING
    permissions: List[str] = Field(default_factory=list)
    resource_limits: Dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(default=300.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id", "task_id")
    @classmethod
    def validate_context_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v
