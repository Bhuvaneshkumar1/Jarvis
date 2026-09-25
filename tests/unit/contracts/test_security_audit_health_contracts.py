from pydantic import ValidationError
import pytest
from jarvis.core.contracts.security import PolicyDecisionContract, ApprovalContract
from jarvis.core.contracts.verification import VerificationContract
from jarvis.core.contracts.audit import AuditEventContract
from jarvis.core.contracts.integrations import IntegrationContract
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.enums import PolicyDecisionType, RiskLevel, ApprovalStatus, VerificationResultStatus, AuditSeverity, IntegrationStatus, HealthState


def test_security_contracts():
    policy = PolicyDecisionContract(
        action="GIT_PUSH",
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason="Git push requires explicit user approval",
        risk_level=RiskLevel.HIGH,
    )
    assert policy.decision == PolicyDecisionType.REQUIRE_APPROVAL

    approval = ApprovalContract(
        task_id="task-99",
        requested_action="GIT_PUSH",
        status=ApprovalStatus.PENDING,
    )
    assert approval.approval_id.startswith("appr-")


def test_verification_contract_immutability():
    ver = VerificationContract(
        task_id="task-10",
        expected_state="file_exists",
        observed_state="file_exists",
        result=VerificationResultStatus.PASSED,
    )
    assert ver.result == VerificationResultStatus.PASSED
    with pytest.raises(ValidationError):
        ver.result = VerificationResultStatus.FAILED


def test_audit_event_immutability():
    evt = AuditEventContract(
        component="PolicyEngine",
        action="EVALUATE",
        severity=AuditSeverity.INFO,
    )
    assert evt.event_id.startswith("evt-")
    with pytest.raises(ValidationError):
        evt.action = "MUTATED"


def test_integration_and_health_contracts():
    integ = IntegrationContract(provider="GitHub", capability="CODE_COMMIT", status=IntegrationStatus.CONNECTED)
    assert integ.provider == "GitHub"

    health = HealthStatusContract(component="Database", status=HealthState.HEALTHY, latency=0.002)
    assert health.latency == 0.002
