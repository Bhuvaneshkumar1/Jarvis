"""
Unit, Risk Classification, Scope & Security Tests for Centralized Policy Engine (Batch 15).
"""

import os
import pytest
import tempfile
from jarvis.security.policy import (
    PolicyEngine,
    AuthorizationRequest,
    Principal,
    PrincipalType,
    RiskLevel,
    PolicyDecisionType,
    CyberAuthorizationContext,
    CyberScopeCategory,
    classify_risk,
    normalize_resource_path,
    is_path_in_scope,
    validate_delegation,
    DelegationError,
)


def test_principal_validation():
    p = Principal(principal_id="user_1", principal_type=PrincipalType.USER, permissions=["filesystem.read"])
    assert p.principal_id == "user_1"
    assert p.principal_type == PrincipalType.USER

    with pytest.raises(ValueError):
        Principal(principal_id="  ", principal_type=PrincipalType.USER)


def test_permission_grant_and_explicit_denial():
    engine = PolicyEngine()

    # Principal without permission
    p1 = Principal(principal_id="user_no_perm", principal_type=PrincipalType.USER, permissions=[])
    req1 = AuthorizationRequest(principal=p1, action="filesystem.read", resource="D:\\test.txt")
    dec1 = engine.evaluate(req1)
    assert not dec1.allowed
    assert dec1.reason_code == "PERMISSION_DENIED"

    # Principal with permission
    p2 = Principal(principal_id="user_perm", principal_type=PrincipalType.USER, permissions=["filesystem.read"])
    req2 = AuthorizationRequest(principal=p2, action="filesystem.read", resource="D:\\test.txt")
    dec2 = engine.evaluate(req2)
    assert dec2.allowed
    assert dec2.decision == PolicyDecisionType.ALLOW


def test_risk_classification_and_downgrade_prevention():
    # Base risk classification
    r_read = classify_risk(action="filesystem.read", resource="D:\\test.txt")
    assert r_read == RiskLevel.LOW

    r_modify = classify_risk(action="filesystem.modify", resource="D:\\test.txt")
    assert r_modify == RiskLevel.MEDIUM

    r_delete = classify_risk(action="filesystem.delete", resource="D:\\test.txt")
    assert r_delete == RiskLevel.HIGH

    # Sensitive path escalation
    r_sens = classify_risk(action="filesystem.read", resource="C:\\Windows\\System32\\config\\sam")
    assert r_sens == RiskLevel.CRITICAL

    # Bulk operation escalation
    r_bulk = classify_risk(action="filesystem.delete", resource="D:\\test.txt", metadata={"bulk_operation": True})
    assert r_bulk == RiskLevel.CRITICAL

    # Attempted risk downgrade prevention: caller passing requested_risk=LOW for a delete operation
    r_downgrade_attempt = classify_risk(
        action="filesystem.delete",
        resource="D:\\test.txt",
        requested_risk=RiskLevel.LOW,
    )
    assert r_downgrade_attempt == RiskLevel.HIGH  # Downgrade ignored, keeps HIGH!


def test_windows_path_normalization_and_traversal_protection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sub_dir = os.path.join(tmp_dir, "subdir")
        os.makedirs(sub_dir, exist_ok=True)
        file_path = os.path.join(sub_dir, "file.txt")
        with open(file_path, "w") as f:
            f.write("content")

        norm_path = normalize_resource_path(file_path)
        assert os.path.isabs(norm_path)

        # Path traversal check
        traversal_path = os.path.join(sub_dir, "..", "subdir", "file.txt")
        assert is_path_in_scope(traversal_path, tmp_dir)

        # Outside scope check
        outside_path = os.path.join(tmp_dir, "..", "outside.txt")
        assert not is_path_in_scope(outside_path, sub_dir)


def test_cybersecurity_scope_validation_and_unknown_target_denial():
    engine = PolicyEngine()
    p = Principal(principal_id="sec_agent", principal_type=PrincipalType.AGENT, permissions=["security.scan", "security.exploit"])

    # Missing cyber context
    req_no_ctx = AuthorizationRequest(principal=p, action="security.scan", resource="https://target.local")
    dec_no_ctx = engine.evaluate(req_no_ctx)
    assert not dec_no_ctx.allowed

    # Unknown target
    cyber_ctx_unknown = CyberAuthorizationContext(
        target_identifier="https://target.local",
        authorization_owner="user",
        permitted_scope="lab",
        scope_category=CyberScopeCategory.UNKNOWN_TARGET,
    )
    req_unknown = AuthorizationRequest(
        principal=p,
        action="security.scan",
        resource="https://target.local",
        cyber_context=cyber_ctx_unknown,
    )
    dec_unknown = engine.evaluate(req_unknown)
    assert not dec_unknown.allowed
    assert "CYBER" in dec_unknown.reason_code

    # Authorized local lab target
    cyber_ctx_lab = CyberAuthorizationContext(
        target_identifier="127.0.0.1",
        authorization_owner="user",
        permitted_scope="local_lab",
        scope_category=CyberScopeCategory.LOCAL_LAB,
    )
    req_lab = AuthorizationRequest(
        principal=p,
        action="security.scan",
        resource="127.0.0.1",
        cyber_context=cyber_ctx_lab,
    )
    dec_lab = engine.evaluate(req_lab)
    assert dec_lab.allowed


def test_agent_delegation_restrictions():
    parent = Principal(
        principal_id="parent_agent",
        principal_type=PrincipalType.AGENT,
        permissions=["filesystem.read", "filesystem.create"],
        delegation_depth=1,
    )

    # Valid delegation
    validate_delegation(parent, ["filesystem.read"])

    # Escalation attempt: delegating permission parent lacks
    with pytest.raises(DelegationError):
        validate_delegation(parent, ["filesystem.delete"])

    # Escalation attempt: delegating forbidden permission
    with pytest.raises(DelegationError):
        validate_delegation(parent, ["system.shutdown"])


def test_fail_closed_behavior():
    engine = PolicyEngine()
    # Request with None principal
    req_bad = AuthorizationRequest(
        principal=Principal(principal_id="test", principal_type=PrincipalType.USER), action="filesystem.read", resource="D:\\test.txt"
    )
    req_bad.principal = None  # type: ignore
    dec = engine.evaluate(req_bad)
    assert not dec.allowed
    assert dec.decision == PolicyDecisionType.DENY
