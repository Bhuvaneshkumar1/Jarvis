from typing import Callable, Dict, Any, Optional
from pydantic import BaseModel
from jarvis.core.policy import PolicyEngine, ActionRequest, ActionType, RiskLevel
from jarvis.core.verification import VerificationEngine
from jarvis.core.audit_log import AuditLogger

class ToolDefinition(BaseModel):
    name: str
    description: str
    action_type: ActionType
    risk_level: RiskLevel = RiskLevel.LOW

class ToolExecutionResult(BaseModel):
    success: bool
    tool_name: str
    output: Any = None
    error: Optional[str] = None
    policy_allowed: bool = True
    verified: bool = False
    verification_details: Dict[str, Any] = {}

class ToolRegistry:
    """
    Unified Tool Registry enforcing Policy Check -> Execution -> Postcondition Verification -> Audit.
    Rule 9 & Rule 11.
    """

    def __init__(self, policy_engine: Optional[PolicyEngine] = None, audit_logger: Optional[AuditLogger] = None):
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit_logger = audit_logger or AuditLogger()
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        action_type: ActionType,
        handler: Callable[..., Any],
        risk_level: RiskLevel = RiskLevel.LOW,
    ):
        tool_def = ToolDefinition(
            name=name,
            description=description,
            action_type=action_type,
            risk_level=risk_level,
        )
        self._tools[name] = tool_def
        self._handlers[name] = handler

    def execute_tool(
        self,
        name: str,
        kwargs: Dict[str, Any],
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        user_approved: bool = False,
        task_has_explicit_modify_approval: bool = False,
        postcondition_verifier: Optional[Callable[[Any], Any]] = None,
    ) -> ToolExecutionResult:
        if name not in self._tools:
            err = f"Tool '{name}' is not registered in ToolRegistry."
            self.audit_logger.log_event(
                component="ToolRegistry",
                action="EXECUTE_TOOL",
                result="FAILED",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
                verification_state="FAILED",
                error=err,
            )
            return ToolExecutionResult(success=False, tool_name=name, error=err, policy_allowed=False)

        tool_def = self._tools[name]
        target_str = str(kwargs.get("path") or kwargs.get("target") or name)

        # 1. Policy Evaluation
        action_req = ActionRequest(
            action_type=tool_def.action_type,
            target=target_str,
            risk_level=tool_def.risk_level,
            user_approved=user_approved,
            task_has_explicit_modify_approval=task_has_explicit_modify_approval,
        )
        decision = self.policy_engine.evaluate(action_req)
        if not decision.allowed:
            err = f"Policy denied execution of tool '{name}': {decision.reason}"
            self.audit_logger.log_event(
                component="ToolRegistry",
                action=f"EXECUTE_{name}",
                result="DENIED",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
                verification_state="POLICY_DENIED",
                error=err,
                details={"target": target_str, "risk_level": tool_def.risk_level.value},
            )
            return ToolExecutionResult(
                success=False,
                tool_name=name,
                error=err,
                policy_allowed=False,
            )

        # 2. Execution
        handler = self._handlers[name]
        try:
            output = handler(**kwargs)
        except Exception as e:
            err_msg = f"Exception during execution of tool '{name}': {str(e)}"
            self.audit_logger.log_event(
                component="ToolRegistry",
                action=f"EXECUTE_{name}",
                result="EXCEPTION",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
                verification_state="FAILED",
                error=err_msg,
            )
            return ToolExecutionResult(
                success=False,
                tool_name=name,
                error=err_msg,
                policy_allowed=True,
                verified=False,
            )

        # 3. Postcondition Verification (Rule 11)
        verified = True
        ver_details = {}
        if postcondition_verifier:
            ver_res = postcondition_verifier(output)
            if hasattr(ver_res, "passed"):
                verified = ver_res.passed
                ver_details = ver_res.details if hasattr(ver_res, "details") else {}
            elif isinstance(ver_res, bool):
                verified = ver_res

        ver_state = "VERIFIED" if verified else "VERIFICATION_FAILED"

        # 4. Audit Logging
        self.audit_logger.log_event(
            component="ToolRegistry",
            action=f"EXECUTE_{name}",
            result="SUCCESS" if verified else "POSTCONDITION_FAILED",
            task_id=task_id,
            correlation_id=correlation_id,
            agent_id=agent_id,
            verification_state=ver_state,
            details={"target": target_str, "verified": verified, "verification_details": ver_details},
        )

        return ToolExecutionResult(
            success=verified,
            tool_name=name,
            output=output,
            error=None if verified else "Postcondition verification failed.",
            policy_allowed=True,
            verified=verified,
            verification_details=ver_details,
        )
