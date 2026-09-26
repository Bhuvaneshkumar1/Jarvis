"""
Least-Privilege Secret Access Policy & Audit Authorization Engine (Batch 10).
"""

from typing import Dict, Set, Optional

from jarvis.core.audit_log import AuditLogger
from jarvis.core.secrets.models import (
    SecretAccessRequest,
    SecretAccessResult,
    SecretClassification,
)


class SecretPolicyEvaluator:
    """
    Evaluates least-privilege access control policies for secret retrieval.
    Prevents unauthorized components from requesting arbitrary secrets.
    """

    # Component Authorization Registry: requester -> set of allowed secret identifiers
    DEFAULT_COMPONENT_PERMISSIONS: Dict[str, Set[str]] = {
        "llm_router": {
            "NVIDIA_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "LOCAL_LLM_URL",
        },
        "telegram": {
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_ALLOWED_CHAT_IDS",
        },
        "github": {
            "GITHUB_TOKEN",
            "GITHUB_FINE_GRAINED_TOKEN",
        },
        "database": {
            "DATABASE_PASSWORD",
            "JARVIS_DATABASE_PATH",
        },
        "system_admin": {"*"},
        "runtime": {"*"},
        "test_runner": {"*"},
    }

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        custom_permissions: Optional[Dict[str, Set[str]]] = None,
    ):
        self.audit_logger = audit_logger or AuditLogger()
        self.permissions: Dict[str, Set[str]] = custom_permissions or self.DEFAULT_COMPONENT_PERMISSIONS

    def evaluate(self, request: SecretAccessRequest, target_classification: SecretClassification) -> SecretAccessResult:
        """
        Evaluates authorization policy for secret request.
        Logs structured audit record (SECRET_ACCESS) with ZERO raw secret leakage.
        """
        requester = request.requester
        identifier = request.secret_identifier

        # Rule 1: CRITICAL_SECRET requires system_admin or runtime privileges
        if target_classification == SecretClassification.CRITICAL_SECRET:
            if requester not in ("system_admin", "runtime", "test_runner"):
                reason = f"CRITICAL_SECRET '{identifier}' access denied for non-admin component '{requester}'."
                self._log_audit_decision(request, target_classification, allowed=False, reason=reason)
                return SecretAccessResult(allowed=False, secret_identifier=identifier, reason=reason)

        # Rule 2: Least privilege component scoping check
        allowed_secrets = self.permissions.get(requester)
        if allowed_secrets is None:
            # Unregistered component defaults to denying SECRET / CRITICAL_SECRET
            if target_classification in (SecretClassification.SECRET, SecretClassification.CRITICAL_SECRET):
                reason = f"Unregistered component '{requester}' denied access to secret '{identifier}'."
                self._log_audit_decision(request, target_classification, allowed=False, reason=reason)
                return SecretAccessResult(allowed=False, secret_identifier=identifier, reason=reason)
        elif "*" not in allowed_secrets and identifier not in allowed_secrets:
            reason = f"Component '{requester}' is not scoped to access secret '{identifier}'."
            self._log_audit_decision(request, target_classification, allowed=False, reason=reason)
            return SecretAccessResult(allowed=False, secret_identifier=identifier, reason=reason)

        # Authorized cleanly
        reason = "Authorized"
        audit_id = self._log_audit_decision(request, target_classification, allowed=True, reason=reason)
        return SecretAccessResult(allowed=True, secret_identifier=identifier, reason=reason, audit_id=audit_id)

    def _log_audit_decision(
        self,
        request: SecretAccessRequest,
        classification: SecretClassification,
        allowed: bool,
        reason: str,
    ) -> str:
        """Emits structured audit log event containing ONLY non-sensitive metadata."""
        decision_str = "ALLOW" if allowed else "DENY"
        action_name = f"SECRET_{request.requested_operation.value.upper()}"
        filepath = self.audit_logger.log_event(
            component="SecretsManager",
            action=action_name,
            result="SUCCESS" if allowed else "DENIED",
            correlation_id=request.correlation_id,
            details={
                "secret_identifier": request.secret_identifier,
                "classification": classification.value,
                "decision": decision_str,
                "reason": reason,
                "purpose": request.purpose,
            },
        )
        return filepath
