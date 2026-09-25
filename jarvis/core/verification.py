import os
from typing import Any, Dict, Optional
from pydantic import BaseModel


class PreconditionResult(BaseModel):
    passed: bool
    reason: str
    details: Dict[str, Any] = {}


class PostconditionResult(BaseModel):
    passed: bool
    reason: str
    details: Dict[str, Any] = {}


class VerificationResult(BaseModel):
    verified: bool
    stage_failed: Optional[str] = None
    reason: str
    precondition_result: Optional[PreconditionResult] = None
    postcondition_result: Optional[PostconditionResult] = None


class VerificationEngine:
    """
    Verification Engine enforcing Rule 11:
    PRECONDITION → POLICY CHECK → EXECUTION → POSTCONDITION → VERIFICATION → AUDIT.
    Does NOT accept text claims or LLM responses as proof of execution success.
    """

    @staticmethod
    def verify_file_created(filepath: str, min_bytes: int = 1) -> PostconditionResult:
        if not os.path.exists(filepath):
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: File '{filepath}' does not exist on disk.",
                details={"filepath": filepath},
            )
        size = os.path.getsize(filepath)
        if size < min_bytes:
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: File '{filepath}' size ({size} bytes) is less than minimum required ({min_bytes} bytes).",
                details={"filepath": filepath, "size": size, "min_bytes": min_bytes},
            )
        return PostconditionResult(
            passed=True,
            reason=f"Verification succeeded: File '{filepath}' exists with size {size} bytes.",
            details={"filepath": filepath, "size": size},
        )

    @staticmethod
    def verify_file_modified(filepath: str, original_mtime: float) -> PostconditionResult:
        if not os.path.exists(filepath):
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: Target file '{filepath}' missing after modification.",
                details={"filepath": filepath},
            )
        new_mtime = os.path.getmtime(filepath)
        if new_mtime <= original_mtime:
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: File '{filepath}' mtime was not updated.",
                details={"original_mtime": original_mtime, "new_mtime": new_mtime},
            )
        return PostconditionResult(
            passed=True,
            reason=f"Verification succeeded: File '{filepath}' mtime updated.",
            details={"original_mtime": original_mtime, "new_mtime": new_mtime},
        )

    @staticmethod
    def verify_file_deleted(filepath: str) -> PostconditionResult:
        if os.path.exists(filepath):
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: Target file '{filepath}' still exists on disk.",
                details={"filepath": filepath},
            )
        return PostconditionResult(
            passed=True,
            reason=f"Verification succeeded: File '{filepath}' successfully removed.",
            details={"filepath": filepath},
        )

    @staticmethod
    def verify_command_result(exit_code: int, expected_exit_code: int = 0) -> PostconditionResult:
        if exit_code != expected_exit_code:
            return PostconditionResult(
                passed=False,
                reason=f"Verification failed: Command exit code {exit_code} != expected {expected_exit_code}.",
                details={"exit_code": exit_code, "expected": expected_exit_code},
            )
        return PostconditionResult(
            passed=True,
            reason=f"Verification succeeded: Command exit code matches {expected_exit_code}.",
            details={"exit_code": exit_code},
        )
