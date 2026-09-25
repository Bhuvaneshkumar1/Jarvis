from jarvis.core.policy import PolicyEngine, ActionRequest, ActionType, RiskLevel


def test_read_allowed_by_default():
    engine = PolicyEngine()
    req = ActionRequest(action_type=ActionType.READ, target="some_file.txt")
    decision = engine.evaluate(req)
    assert decision.allowed is True
    assert decision.requires_user_approval is False


def test_delete_requires_approval():
    engine = PolicyEngine()
    req = ActionRequest(action_type=ActionType.DELETE, target="important.db")
    decision = engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_user_approval is True

    # When user approves
    req_approved = ActionRequest(action_type=ActionType.DELETE, target="important.db", user_approved=True)
    decision_approved = engine.evaluate(req_approved)
    assert decision_approved.allowed is True


def test_fail_closed_unrecognized_risk():
    engine = PolicyEngine()
    req = ActionRequest(action_type=ActionType.EXTERNAL_API_CALL, target="http://unknown", risk_level=RiskLevel.HIGH)
    decision = engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_user_approval is True
