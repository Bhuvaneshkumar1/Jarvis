"""
Centralized Shared Enums for JARVIS Core Contracts (Section 24).
"""

from enum import Enum


class RequestSource(str, Enum):
    VOICE = "VOICE"
    TELEGRAM = "TELEGRAM"
    LOCAL_UI = "LOCAL_UI"
    SYSTEM = "SYSTEM"
    SCHEDULE = "SCHEDULE"
    AGENT = "AGENT"


class InputType(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"
    FILE = "FILE"
    EVENT = "EVENT"
    SYSTEM = "SYSTEM"


class OutputType(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    FILE = "FILE"
    UI = "UI"
    ACTION = "ACTION"
    SYSTEM = "SYSTEM"


class ResponseStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    URGENT = "URGENT"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentStatus(str, Enum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class ToolResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"


class MemoryScope(str, Enum):
    WORKING = "WORKING"
    CONVERSATION = "CONVERSATION"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROJECT = "PROJECT"
    PERSONAL = "PERSONAL"
    PREFERENCE = "PREFERENCE"
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"


class MessageRole(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    TOOL = "TOOL"


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_AUTHENTICATION = "REQUIRE_AUTHENTICATION"
    REQUIRE_AUTHORIZATION = "REQUIRE_AUTHORIZATION"
    BLOCK = "BLOCK"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class VerificationResultStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    NOT_VERIFIED = "NOT_VERIFIED"


class AuditSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    SECURITY = "SECURITY"


class IntegrationStatus(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    DEGRADED = "DEGRADED"
    PENDING_AUTH = "PENDING_AUTH"


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
