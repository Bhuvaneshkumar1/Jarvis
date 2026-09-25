"""
LLMRequest and LLMResponse Provider-Neutral Contract Definitions (Section 17).
"""

import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import MessageRole

class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None

class LLMRequestContract(BaseModel):
    request_id: str = Field(default_factory=lambda: f"llmreq-{uuid.uuid4().hex[:12]}")
    model: str = Field(..., min_length=1)
    messages: List[ChatMessage] = Field(..., min_length=1)
    system_context: Optional[str] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    timeout: float = Field(default=60.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty or whitespace.")
        return v

class LLMResponseContract(BaseModel, frozen=True):
    request_id: str
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, int] = Field(default_factory=dict)
    finish_reason: str = Field(default="stop")
    latency: float = Field(default=0.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def validate_response_request_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty or whitespace.")
        return v
