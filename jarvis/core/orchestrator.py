from typing import Dict, Any, Optional, Callable
from jarvis.core.task_manager import TaskManager, TaskState
from jarvis.core.agent_manager import AgentManager
from jarvis.core.policy import PolicyEngine, ActionRequest, ActionType, RiskLevel
from jarvis.core.rollback import RollbackManager
from jarvis.core.tool_registry import ToolRegistry
from jarvis.core.llm_router import LLMRouter
from jarvis.core.memory import MemoryRetrievalEngine
from jarvis.core.audit_log import AuditLogger
from jarvis.core.resource_monitor import ResourceMonitor

class Orchestrator:
    """
    Central JARVIS Orchestrator.
    Executes tasks following the mandatory pipeline architecture:
    REQUEST -> UNDERSTAND -> RETRIEVE -> PLAN -> AUTHORIZE -> DELEGATE -> EXECUTE -> VERIFY -> RECOVER/ROLLBACK -> REMEMBER -> REPORT
    """

    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        agent_manager: Optional[AgentManager] = None,
        policy_engine: Optional[PolicyEngine] = None,
        tool_registry: Optional[ToolRegistry] = None,
        audit_logger: Optional[AuditLogger] = None,
        memory_engine: Optional[MemoryRetrievalEngine] = None,
        llm_router: Optional[LLMRouter] = None,
    ):
        self.audit_logger = audit_logger or AuditLogger()
        self.task_manager = task_manager or TaskManager()
        self.agent_manager = agent_manager or AgentManager()
        self.policy_engine = policy_engine or PolicyEngine()
        self.tool_registry = tool_registry or ToolRegistry(self.policy_engine, self.audit_logger)
        self.memory_engine = memory_engine or MemoryRetrievalEngine()
        self.llm_router = llm_router or LLMRouter()

    def process_request(
        self,
        request_text: str,
        user_approved: bool = False,
        execution_handler: Optional[Callable[[Dict[str, Any], RollbackManager], Any]] = None,
        postcondition_verifier: Optional[Callable[[Any], Any]] = None,
    ) -> Dict[str, Any]:
        # 1. REQUEST
        task_record = self.task_manager.create_task(description=request_text)
        task_id = task_record.task_id
        correlation_id = task_record.correlation_id

        self.audit_logger.log_event(
            component="Orchestrator",
            action="PIPELINE_START",
            result="STARTED",
            task_id=task_id,
            correlation_id=correlation_id,
            details={"request_text": request_text},
        )

        rollback_mgr = RollbackManager()

        try:
            # Resource Health Check
            mem_health = ResourceMonitor.check_memory_health()
            if not mem_health["healthy"]:
                raise RuntimeError(mem_health["message"])

            # 2. UNDERSTAND
            self.task_manager.update_state(task_id, TaskState.PLANNING)
            understanding = self.llm_router.route_and_generate(
                prompt=f"Understand request: {request_text}",
                system_instruction="Analyze request requirements and determine parameters.",
            )

            # 3. RETRIEVE
            context_memories = self.memory_engine.retrieve_memory(query=request_text)

            # 4. PLAN
            plan = {
                "steps": [
                    {"action": "EXECUTE_TASK_LOGIC", "target": request_text},
                ],
                "context": context_memories,
                "understanding": understanding["text"],
            }

            # 5. AUTHORIZE
            action_type = ActionType.MODIFY if "modify" in request_text.lower() or "update" in request_text.lower() else ActionType.CREATE
            action_req = ActionRequest(
                action_type=action_type,
                target=request_text,
                risk_level=RiskLevel.MEDIUM,
                user_approved=user_approved,
            )
            policy_decision = self.policy_engine.evaluate(action_req)

            if not policy_decision.allowed:
                self.task_manager.update_state(
                    task_id, TaskState.FAILED, error=policy_decision.reason, verification_state="POLICY_DENIED"
                )
                self.audit_logger.log_event(
                    component="Orchestrator",
                    action="POLICY_CHECK",
                    result="DENIED",
                    task_id=task_id,
                    correlation_id=correlation_id,
                    verification_state="POLICY_DENIED",
                    error=policy_decision.reason,
                )
                return {
                    "status": "DENIED",
                    "task_id": task_id,
                    "reason": policy_decision.reason,
                    "requires_approval": policy_decision.requires_user_approval,
                }

            # 6. DELEGATE (Spawn dynamic temporary agent)
            self.task_manager.update_state(task_id, TaskState.EXECUTING)
            temp_agent = self.agent_manager.spawn_agent(
                role="ExecutionSubagent", task_id=task_id, memory_limit_mb=1024
            )
            agent_id = temp_agent.config.agent_id

            self.audit_logger.log_event(
                component="Orchestrator",
                action="SPAWN_AGENT",
                result="SUCCESS",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
            )

            # 7. EXECUTE
            def _runner():
                if execution_handler:
                    return execution_handler(plan, rollback_mgr)
                return f"Default execution output for: {request_text}"

            execution_output = temp_agent.execute_task(_runner)

            # 8. VERIFY (Rule 11)
            self.task_manager.update_state(task_id, TaskState.VERIFYING)
            verified = True
            verification_reason = "Executed successfully."
            if postcondition_verifier:
                v_res = postcondition_verifier(execution_output)
                if hasattr(v_res, "passed"):
                    verified = v_res.passed
                    verification_reason = v_res.reason
                elif isinstance(v_res, bool):
                    verified = v_res

            if not verified:
                raise RuntimeError(f"Postcondition verification failed: {verification_reason}")

            # 9. REMEMBER
            self.memory_engine.store_memory(
                key=f"task-{task_id}", content=f"Request: {request_text} | Result: {str(execution_output)[:100]}"
            )

            # 10. REPORT
            self.task_manager.update_state(
                task_id, TaskState.COMPLETED, result=execution_output, verification_state="VERIFIED"
            )
            self.audit_logger.log_event(
                component="Orchestrator",
                action="PIPELINE_COMPLETE",
                result="SUCCESS",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
                verification_state="VERIFIED",
                details={"execution_output": str(execution_output)[:200]},
            )

            return {
                "status": "COMPLETED",
                "task_id": task_id,
                "correlation_id": correlation_id,
                "agent_id": agent_id,
                "output": execution_output,
                "verification_state": "VERIFIED",
            }

        except Exception as ex:
            err_msg = str(ex)
            # 8. RECOVER / ROLLBACK (Rule 12)
            self.audit_logger.log_event(
                component="Orchestrator",
                action="EXECUTION_FAILED",
                result="INITIATING_ROLLBACK",
                task_id=task_id,
                correlation_id=correlation_id,
                error=err_msg,
            )
            rollback_res = rollback_mgr.execute_rollback()

            self.task_manager.update_state(
                task_id, TaskState.ROLLED_BACK, error=err_msg, verification_state="ROLLED_BACK"
            )

            self.audit_logger.log_event(
                component="Orchestrator",
                action="ROLLBACK_COMPLETE",
                result="ROLLED_BACK",
                task_id=task_id,
                correlation_id=correlation_id,
                verification_state="ROLLED_BACK",
                details=rollback_res,
            )

            return {
                "status": "FAILED",
                "task_id": task_id,
                "correlation_id": correlation_id,
                "error": err_msg,
                "rollback_details": rollback_res,
                "verification_state": "ROLLED_BACK",
            }
        finally:
            rollback_mgr.cleanup()
