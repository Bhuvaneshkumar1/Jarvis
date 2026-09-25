"""
Centralized Exception Hierarchy for JARVIS AI OS.
"""

class JarvisError(Exception):
    """Base exception class for all JARVIS errors."""
    pass

class ConfigurationError(JarvisError):
    """Raised when configuration validation fails or required environment variables are missing."""
    pass

class AuthenticationError(JarvisError):
    """Raised when authentication credentials or token validation fails."""
    pass

class AuthorizationError(JarvisError):
    """Raised when an operation violates security policy or lacks required user approval."""
    pass

class ToolError(JarvisError):
    """Raised when tool execution fails or tool input parameters are invalid."""
    pass

class AgentError(JarvisError):
    """Raised when dynamic agent spawning, execution, or isolation fails."""
    pass

class MemoryError(JarvisError):
    """Raised when memory store indexing or retrieval fails."""
    pass

class IntegrationError(JarvisError):
    """Raised when external service adapter integration encounters an operational failure."""
    pass

class VerificationError(JarvisError):
    """Raised when empirical postcondition or precondition checks fail."""
    pass

class TaskError(JarvisError):
    """Raised when task state transition or tracking fails."""
    pass

class ResourceLimitError(JarvisError):
    """Raised when memory, CPU, or process resource budgets are exceeded."""
    pass
