"""
Centralized Risk Classification & Risk Escalation Engine for JARVIS (Batch 15).
"""

from typing import Dict, Any, Optional
from jarvis.security.policy.models import RiskLevel, Principal, PrincipalType
from jarvis.security.policy.permissions import normalize_permission_name

# Default Base Risk Table
BASE_RISK_MAP: Dict[str, RiskLevel] = {
    "filesystem.read": RiskLevel.LOW,
    "filesystem.create": RiskLevel.LOW,
    "filesystem.modify": RiskLevel.MEDIUM,
    "filesystem.rename": RiskLevel.MEDIUM,
    "filesystem.move": RiskLevel.MEDIUM,
    "filesystem.delete": RiskLevel.HIGH,
    "filesystem.execute": RiskLevel.HIGH,
    "system.app.launch": RiskLevel.LOW,
    "system.app.close": RiskLevel.MEDIUM,
    "system.process.inspect": RiskLevel.LOW,
    "system.process.terminate": RiskLevel.MEDIUM,
    "system.settings.read": RiskLevel.LOW,
    "system.settings.modify": RiskLevel.HIGH,
    "system.shutdown": RiskLevel.CRITICAL,
    "system.restart": RiskLevel.CRITICAL,
    "code.read": RiskLevel.LOW,
    "code.create": RiskLevel.LOW,
    "code.modify": RiskLevel.MEDIUM,
    "code.delete": RiskLevel.HIGH,
    "code.test": RiskLevel.LOW,
    "code.build": RiskLevel.MEDIUM,
    "git.status": RiskLevel.LOW,
    "git.commit": RiskLevel.HIGH,
    "git.push": RiskLevel.HIGH,
    "agent.inspect": RiskLevel.LOW,
    "agent.create": RiskLevel.MEDIUM,
    "agent.spawn": RiskLevel.MEDIUM,
    "agent.delegate": RiskLevel.MEDIUM,
    "agent.terminate": RiskLevel.HIGH,
    "integration.read": RiskLevel.LOW,
    "integration.write": RiskLevel.MEDIUM,
    "integration.send": RiskLevel.HIGH,
    "integration.delete": RiskLevel.HIGH,
    "security.recon": RiskLevel.LOW,
    "security.scan": RiskLevel.MEDIUM,
    "security.analyze": RiskLevel.LOW,
    "security.exploit": RiskLevel.CRITICAL,
    "security.credential_test": RiskLevel.HIGH,
    "security.modify_target": RiskLevel.CRITICAL,
}

RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _escalate_risk(current: RiskLevel, target: RiskLevel) -> RiskLevel:
    """Return higher risk level of current and target."""
    return max(current, target, key=lambda r: RISK_ORDER.index(r))


def classify_risk(
    action: str,
    resource: str,
    principal: Optional[Principal] = None,
    requested_risk: Optional[RiskLevel] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RiskLevel:
    """
    Deterministically classify the effective risk of an operation.
    Enforces risk escalation rules and prevents agents/tools from downgrading risk.
    """
    metadata = metadata or {}
    perm_norm = normalize_permission_name(action)

    # 1. Base classification from action
    base_risk = BASE_RISK_MAP.get(perm_norm, RiskLevel.MEDIUM)

    effective_risk = base_risk

    # 2. Risk Escalation Rules

    # A. Bulk operations (e.g., deleting or modifying multiple files)
    if metadata.get("bulk_operation") or metadata.get("affected_count", 1) > 5:
        effective_risk = _escalate_risk(effective_risk, RiskLevel.CRITICAL)

    # B. Sensitive directories (e.g. C:\Windows, System32, data/credentials, secrets)
    resource_lower = resource.lower()
    sensitive_keywords = ["system32", "windows", "credentials", "secrets", "shadow", "etc/passwd", "sam", "config/master"]
    if any(kw in resource_lower for kw in sensitive_keywords):
        effective_risk = _escalate_risk(effective_risk, RiskLevel.CRITICAL)

    # C. External network / production endpoints
    if metadata.get("is_production") or metadata.get("external_service"):
        effective_risk = _escalate_risk(effective_risk, RiskLevel.HIGH)

    # D. Irreversible state changes
    if metadata.get("irreversible") or metadata.get("destructive"):
        effective_risk = _escalate_risk(effective_risk, RiskLevel.HIGH)

    # E. Broad agent permissions / deep delegation
    if principal and principal.principal_type == PrincipalType.AGENT:
        if principal.delegation_depth > 1:
            effective_risk = _escalate_risk(effective_risk, RiskLevel.HIGH)

    # F. If requested_risk is specified by caller, caller can ONLY escalate risk, never downgrade!
    if requested_risk:
        effective_risk = _escalate_risk(effective_risk, requested_risk)

    return effective_risk
