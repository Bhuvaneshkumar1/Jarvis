"""
Provider-Neutral LLM Contracts, Request/Response Payload Models, and Enums (Batch 20).
"""

import time
import uuid
import re
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from jarvis.core.enums import MessageRole
from jarvis.llm.exceptions import InvalidLLMRequestError

SECRET_METADATA_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{30,}", re.IGNORECASE),
    re.compile(r"xox[bap]-[a-zA-Z0-9\-]+", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
]


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class TaskCategory(str, Enum):
    SIMPLE_CHAT = "SIMPLE_CHAT"
    REASONING = "REASONING"
    CODING = "CODING"
    DEBUGGING = "DEBUGGING"
    RESEARCH = "RESEARCH"
    SUMMARIZATION = "SUMMARIZATION"
    CLASSIFICATION = "CLASSIFICATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    VISION = "VISION"
    TOOL_PLANNING = "TOOL_PLANNING"
    GENERAL = "GENERAL"


class RoutingProfile(str, Enum):
    LATENCY_FIRST = "LATENCY_FIRST"
    COST_AWARE = "COST_AWARE"
    QUALITY_PREFERRED = "QUALITY_PREFERRED"
    PRIVACY_FIRST = "PRIVACY_FIRST"
    BALANCED = "BALANCED"


class LLMProviderState(str, Enum):
    NOT_INITIALIZED = "NOT_INITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class StreamEventType(str, Enum):
    STREAM_STARTED = "STREAM_STARTED"
    TEXT_DELTA = "TEXT_DELTA"
    STRUCTURED_DELTA = "STRUCTURED_DELTA"
    TOOL_CALL_DELTA = "TOOL_CALL_DELTA"
    USAGE_UPDATE = "USAGE_UPDATE"
    STREAM_COMPLETED = "STREAM_COMPLETED"
    STREAM_FAILED = "STREAM_FAILED"
    STREAM_CANCELLED = "STREAM_CANCELLED"


class LLMUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: Optional[int] = Field(default=None, ge=0)
    reasoning_tokens: Optional[int] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def compute_total(self) -> "LLMUsage":
        if self.total_tokens == 0 and (self.input_tokens > 0 or self.output_tokens > 0):
            self.total_tokens = self.input_tokens + self.output_tokens
        return self


class LLMToolCall(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    call_index: int = Field(default=0, ge=0)
    status: str = Field(default="PENDING")

    @field_validator("tool_call_id", "tool_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Tool call fields cannot be empty or whitespace.")
        return v.strip()


class ModelCapability(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: str = Field(..., min_length=1)
    provider_id: str = Field(..., min_length=1)
    supports_text_generation: bool = Field(default=True)
    supports_streaming: bool = Field(default=True)
    supports_structured_output: bool = Field(default=False)
    supports_tool_calling: bool = Field(default=False)
    supports_vision: bool = Field(default=False)
    supports_reasoning: bool = Field(default=False)
    supports_embeddings: bool = Field(default=False)
    context_window: int = Field(default=4096, ge=1)
    max_output_tokens: int = Field(default=2048, ge=1)
    supported_modalities: List[str] = Field(default_factory=lambda: ["text"])


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if v is None:
            raise ValueError("Message content cannot be None.")
        return v


class LLMRequest(BaseModel):
    model_config = {"protected_namespaces": (), "populate_by_name": True}

    request_id: str = Field(default_factory=lambda: f"llmreq-{uuid.uuid4().hex[:12]}")
    model_id: str = Field(..., alias="model", min_length=1)
    messages: List[ChatMessage] = Field(..., min_length=1)
    system_instructions: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    stop_sequences: List[str] = Field(default_factory=list)
    response_format: Optional[Dict[str, Any]] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    timeout: float = Field(default=60.0, ge=0.1, le=600.0)
    stream: bool = Field(default=False)
    data_classification: DataClassification = Field(default=DataClassification.PUBLIC)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    task_category: Optional[TaskCategory] = None
    preferred_provider: Optional[str] = None
    required_capabilities: List[str] = Field(default_factory=list)
    local_only: bool = Field(default=False)
    max_cost: Optional[float] = Field(default=None, ge=0.0)
    max_latency: Optional[float] = Field(default=None, ge=0.0)
    routing_profile: Optional[RoutingProfile] = None

    # Backward compatibility alias for Batch 2 contract
    @property
    def model(self) -> str:
        return self.model_id

    @field_validator("request_id", "model_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise InvalidLLMRequestError("ID field cannot be empty or whitespace.")
        return v.strip()

    @field_validator("metadata")
    @classmethod
    def validate_metadata_secrets(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Prevents arbitrary metadata from carrying unredacted secrets."""
        for key, val in v.items():
            val_str = str(val)
            for pattern in SECRET_METADATA_PATTERNS:
                if pattern.search(val_str):
                    raise ValueError(f"Request metadata key '{key}' contains secret patterns and was rejected.")
        return v

    @model_validator(mode="after")
    def validate_request_bounds(self) -> "LLMRequest":
        if len(self.messages) > 500:
            raise InvalidLLMRequestError("Request exceeds maximum allowed message history limit (500).")
        total_chars = sum(len(m.content) for m in self.messages)
        if self.system_instructions:
            total_chars += len(self.system_instructions)
        if total_chars > 2000000:
            raise InvalidLLMRequestError("Request payload exceeds 2,000,000 character limit.")
        return self


# Alias for Batch 2 backward compatibility
LLMRequestContract = LLMRequest


class LLMResponse(BaseModel, frozen=True):
    model_config = {"protected_namespaces": (), "populate_by_name": True}

    request_id: str = Field(..., min_length=1)
    provider_id: str = Field(..., alias="provider", min_length=1)
    model_id: str = Field(..., alias="model", min_length=1)
    generated_content: Optional[str] = Field(default=None, alias="content")
    finish_reason: str = Field(default="stop")
    usage: Optional[LLMUsage] = None
    latency: float = Field(default=0.0, ge=0.0)
    structured_output: Optional[Dict[str, Any]] = None
    tool_calls: List[LLMToolCall] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    provider_request_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Backward compatibility properties for Batch 2
    @property
    def provider(self) -> str:
        return self.provider_id

    @property
    def model(self) -> str:
        return self.model_id

    @property
    def content(self) -> Optional[str]:
        return self.generated_content

    @field_validator("request_id", "provider_id", "model_id")
    @classmethod
    def validate_response_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Response ID fields cannot be empty or whitespace.")
        return v.strip()


# Alias for Batch 2 backward compatibility
LLMResponseContract = LLMResponse


class LLMStreamEvent(BaseModel):
    model_config = {"protected_namespaces": ()}

    event_id: str = Field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:12]}")
    request_id: str = Field(..., min_length=1)
    event_type: StreamEventType
    text_delta: Optional[str] = None
    structured_delta: Optional[Dict[str, Any]] = None
    tool_call_delta: Optional[LLMToolCall] = None
    usage: Optional[LLMUsage] = None
    finish_reason: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
