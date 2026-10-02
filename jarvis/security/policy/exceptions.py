"""
Policy, Security, and Approval Exceptions for JARVIS (Batch 15).
"""

from jarvis.core.exceptions import JarvisError


class PolicyError(JarvisError):
    """Base exception for all authorization and policy engine errors."""

    pass


class AuthorizationDeniedError(PolicyError):
    """Raised when an operation is explicitly denied by security policy."""

    pass


class ApprovalError(PolicyError):
    """Base exception for all approval-related errors."""

    pass


class ApprovalRequiredError(ApprovalError):
    """Raised when an operation requires explicit approval before execution."""

    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when a requested approval ID is not found."""

    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when an approval has expired."""

    pass


class ApprovalAlreadyConsumedError(ApprovalError):
    """Raised when an approval has already been consumed and cannot be reused."""

    pass


class ApprovalInvalidError(ApprovalError):
    """Raised when an approval decision or state transition is invalid."""

    pass


class ScopeViolationError(PolicyError):
    """Raised when an action or path violates the allowed authorization scope."""

    pass


class DelegationError(PolicyError):
    """Raised when agent permission delegation violates security boundaries or limits."""

    pass


class PolicyConfigurationError(PolicyError):
    """Raised when policy engine configuration is invalid or unsafe."""

    pass


class CyberAuthorizationError(PolicyError):
    """Raised when cybersecurity scope or target authorization is missing or invalid."""

    pass
