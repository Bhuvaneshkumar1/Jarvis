"""
Verification Contract Definitions (Section 20).
"""

import time
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from jarvis.core.enums import VerificationResultStatus


class VerificationContract(BaseModel, frozen=True):
    verification_id: str = Field(default_factory=lambda: f"ver-{uuid.uuid4().hex[:12]}")
    task_id: str
    step_id: Optional[str] = None
    expected_state: str = Field(..., min_length=1)
    observed_state: str = Field(..., min_length=1)
    result: VerificationResultStatus = VerificationResultStatus.NOT_VERIFIED
    verifier: str = Field(default="VerificationEngine")
    timestamp: float = Field(default_factory=time.time)
    evidence: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("verification_id", "task_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ID cannot be empty or whitespace.")
        return v
