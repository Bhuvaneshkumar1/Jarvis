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


class RuntimeLifecycleError(JarvisError):
    """Base class for runtime lifecycle errors."""

    pass


class ComponentInitializationError(RuntimeLifecycleError):
    """Raised when component initialization fails or times out."""

    pass


class ComponentStartError(RuntimeLifecycleError):
    """Raised when starting a component fails or times out."""

    pass


class ComponentStopError(RuntimeLifecycleError):
    """Raised when stopping a component fails or times out."""

    pass


class DependencyCycleError(RuntimeLifecycleError):
    """Raised when a circular dependency is detected between components."""

    pass


class MissingDependencyError(RuntimeLifecycleError):
    """Raised when a component depends on a non-existent component."""

    pass


class DuplicateComponentError(RuntimeLifecycleError):
    """Raised when attempting to register a component with a duplicate name."""

    pass


class InvalidStateTransitionError(RuntimeLifecycleError):
    """Raised when an invalid runtime state transition is requested."""

    pass


class EventBusError(JarvisError):
    """Base exception class for internal event bus errors."""

    pass


class EventPublishError(EventBusError):
    """Raised when publishing an event fails or is attempted after event bus shutdown."""

    pass


class EventDeliveryError(EventBusError):
    """Raised when event delivery to a subscriber fails."""

    pass


class EventSubscriptionError(EventBusError):
    """Raised when subscribing or unsubscribing from the event bus fails."""

    pass


class QueueOverflowError(EventBusError):
    """Raised when event bus queue capacity is exceeded and backpressure policy rejects event."""

    pass
