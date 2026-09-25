"""
Tool, ToolRequest, and ToolResult Contract Definitions (Section 12, Section 13, Section 14).
"""

import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import ToolResultStatus, VerificationResultStatus


class ToolSpecContract(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    required_permission: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolRequestContract(BaseModel):
    call_id: str = Field(default_factory=lambda: f"call-{uuid.uuid4().hex[:12]}")
    task_id: str
    agent_id: Optional[str] = None
    tool_name: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    permission: Optional[str] = None
    timeout: float = Field(default=60.0, ge=0.0)
    correlation_id: Optional[str] = None

    @field_validator("call_id", "task_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v


class ToolResultContract(BaseModel, frozen=True):
    call_id: str
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float = Field(default=0.0, ge=0.0)
    verification_state: VerificationResultStatus = VerificationResultStatus.NOT_VERIFIED
    rollback_available: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("call_id")
    @classmethod
    def validate_call_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("call_id cannot be empty or whitespace.")
        return v
