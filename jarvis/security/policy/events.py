"""
Policy & Approval Security Event Definitions & Audit Integrator for JARVIS (Batch 15).
"""

from typing import Dict, Any, Optional
from jarvis.core.events.contracts import Event
from jarvis.core.audit_log import AuditLogger
from jarvis.security.policy.exceptions import PolicyError


class PolicyEvaluationStartedEvent(Event):
    event_type: str = "PolicyEvaluationStarted"


class PolicyDecisionAllowedEvent(Event):
    event_type: str = "PolicyDecisionAllowed"


class PolicyDecisionDeniedEvent(Event):
    event_type: str = "PolicyDecisionDenied"


class PolicyApprovalRequiredEvent(Event):
    event_type: str = "PolicyApprovalRequired"


class PolicyApprovalCreatedEvent(Event):
    event_type: str = "PolicyApprovalCreated"


class PolicyApprovalRequestedEvent(Event):
    event_type: str = "PolicyApprovalRequested"


class PolicyApprovalApprovedEvent(Event):
    event_type: str = "PolicyApprovalApproved"


class PolicyApprovalRejectedEvent(Event):
    event_type: str = "PolicyApprovalRejected"


class PolicyApprovalExpiredEvent(Event):
    event_type: str = "PolicyApprovalExpired"


class PolicyApprovalCancelledEvent(Event):
    event_type: str = "PolicyApprovalCancelled"


class PolicyApprovalConsumedEvent(Event):
    event_type: str = "PolicyApprovalConsumed"


class PolicyScopeViolationEvent(Event):
    event_type: str = "PolicyScopeViolation"


class PolicyDelegationDeniedEvent(Event):
    event_type: str = "PolicyDelegationDenied"


class PolicyConfigurationChangedEvent(Event):
    event_type: str = "PolicyConfigurationChanged"


class PolicyAuditIntegrator:
    """
    Integrates policy evaluation & approval state transitions with the EventBus and daily AuditLogger.
    Enforces fail-closed behavior if security-critical audit record fails to persist.
    """

    def __init__(self, event_bus: Optional[Any] = None, audit_logger: Optional[AuditLogger] = None):
        self.event_bus = event_bus
        self.audit_logger = audit_logger or AuditLogger()

    def publish_and_log(
        self,
        event: Event,
        component: str = "PolicyEngine",
        action: str = "AUTHORIZATION_CHECK",
        result: str = "SUCCESS",
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        fail_closed: bool = True,
    ) -> None:
        """
        Publish event to event bus (if available) and log to durable daily audit file.
        If fail_closed is True and logging fails, raises PolicyError to prevent silent security bypass.
        """
        details = details or {}
        try:
            # 1. Daily Audit Logger
            self.audit_logger.log_event(
                component=component,
                action=action,
                result=result,
                task_id=task_id,
                correlation_id=correlation_id,
                error=error,
                details=details,
            )
        except Exception as e:
            if fail_closed:
                raise PolicyError(f"Security audit logging failed for policy transition: {str(e)}") from e

        # 2. Event Bus publication
        if self.event_bus:
            try:
                self.event_bus.publish(event)
            except Exception:
                pass  # Event bus failures do not disrupt audit log, but audit log failure is fail-closed
