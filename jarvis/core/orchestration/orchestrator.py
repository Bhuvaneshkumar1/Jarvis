"""
Authoritative Orchestrator & Core Coordinator for JARVIS (Batch 7).
"""

import threading
from collections import deque
from typing import Dict, List, Optional, Any, Callable
from jarvis.core.enums import TaskStatus, TaskPriority, HealthState, RuntimeState
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.logging import JarvisLogger
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.events.bus import EventBus
from jarvis.core.events.contracts import Event
from jarvis.core.tasks import TaskManager
from jarvis.core.audit_log import AuditLogger
from jarvis.core.policy import PolicyEngine, ActionRequest, ActionType, RiskLevel
from jarvis.core.rollback import RollbackManager
from jarvis.core.tool_registry import ToolRegistry
from jarvis.core.llm_router import LLMRouter
from jarvis.core.memory import MemoryRetrievalEngine
from jarvis.core.resource_monitor import ResourceMonitor
from jarvis.core.exceptions import (
    InvalidCommandError,
    TaskNotFoundError,
    InvalidTaskTransitionError,
    TaskValidationError,
)
from jarvis.core.orchestration.contracts import (
    Command,
    CommandResult,
)


class Orchestrator(LifecycleComponent):
    """
    Authoritative JARVIS Core Orchestrator.
    Coordinates application lifecycle, command dispatch, task state management,
    event bus reactions, and graceful shutdown.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        task_manager: Optional[TaskManager] = None,
        logger: Optional[JarvisLogger] = None,
        audit_logger: Optional[AuditLogger] = None,
        policy_engine: Optional[PolicyEngine] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory_engine: Optional[MemoryRetrievalEngine] = None,
        llm_router: Optional[LLMRouter] = None,
        agent_manager: Optional[Any] = None,
    ) -> None:
        self.event_bus: Optional[EventBus] = event_bus
        self.task_manager: TaskManager = task_manager or TaskManager(event_bus=event_bus)
        self.logger: JarvisLogger = logger or JarvisLogger(component="Orchestrator")
        self.audit_logger: AuditLogger = audit_logger or AuditLogger()
        self.policy_engine: PolicyEngine = policy_engine or PolicyEngine()
        self.tool_registry: ToolRegistry = tool_registry or ToolRegistry(self.policy_engine, self.audit_logger)
        self.memory_engine: MemoryRetrievalEngine = memory_engine or MemoryRetrievalEngine()
        self.llm_router: LLMRouter = llm_router or LLMRouter()
        self.agent_manager: Any = agent_manager

        self._context: Optional[RuntimeContext] = None
        self._state: RuntimeState = RuntimeState.STOPPED
        self._lock: threading.Lock = threading.Lock()

        # Bounded operation tracking & history
        self._active_operations: Dict[str, CommandResult] = {}
        self._command_history: deque = deque(maxlen=1000)
        self._subscriptions: List[str] = []

    @property
    def name(self) -> str:
        return "Orchestrator"

    @property
    def dependencies(self) -> List[str]:
        return ["EventBus", "TaskManager"]

    @property
    def state(self) -> RuntimeState:
        return self._state

    async def initialize(self, context: RuntimeContext) -> None:
        """Initialize Orchestrator component."""
        self._context = context
        self.logger.info("Initializing Orchestrator component...")

    async def start(self) -> None:
        """
        Start Orchestrator, subscribe to event bus topics, and set state RUNNING.
        """
        if self._state == RuntimeState.RUNNING:
            return

        self._state = RuntimeState.STARTING

        # Subscribe to Task events on EventBus if available
        if self.event_bus and self.event_bus.state == RuntimeState.RUNNING:
            await self._subscribe_events()

        self._state = RuntimeState.RUNNING
        self.logger.info("Orchestrator started successfully and ready for commands.")

    async def _subscribe_events(self) -> None:
        """Register event listeners on EventBus."""
        if not self.event_bus:
            return

        event_types = [
            "TaskCreated",
            "TaskReady",
            "TaskStarted",
            "TaskPaused",
            "TaskResumed",
            "TaskCompleted",
            "TaskFailed",
            "TaskCancelled",
            "TaskBlocked",
            "TaskUpdated",
        ]
        for evt_type in event_types:
            try:
                sub_id = self.event_bus.subscribe(evt_type, self._handle_task_event)
                self._subscriptions.append(sub_id)
            except Exception as ex:
                self.logger.error(f"Failed to subscribe Orchestrator to event '{evt_type}': {str(ex)}")

    async def _handle_task_event(self, event: Event) -> None:
        """Event reactor callback for task state events."""
        task_id = event.payload.get("task_id") if isinstance(event.payload, dict) else None
        self.logger.info(f"Orchestrator event reaction: [{event.event_type}] for task '{task_id}' (corr: {event.correlation_id})")
        self.audit_logger.log_event(
            component="Orchestrator",
            action=f"EVENT_REACTION_{event.event_type.upper()}",
            result="PROCESSED",
            task_id=task_id,
            correlation_id=event.correlation_id,
            details=event.payload if isinstance(event.payload, dict) else {},
        )

    async def stop(self) -> None:
        """Gracefully stop Orchestrator component."""
        self._state = RuntimeState.STOPPING
        self.logger.info("Orchestrator stopping...")

        # Unsubscribe event listeners
        if self.event_bus and self._subscriptions:
            for sub_id in self._subscriptions:
                try:
                    self.event_bus.unsubscribe(sub_id)
                except Exception:
                    pass
            self._subscriptions.clear()

        self._state = RuntimeState.STOPPED
        self.logger.info("Orchestrator stopped.")

    def execute_command(self, command: Command) -> CommandResult:
        """
        Authoritative Command Handler.
        Validates command, enforces idempotency, coordinates state transition,
        logs audit trail, and returns serializable CommandResult.
        """
        if self._state not in (RuntimeState.RUNNING, RuntimeState.STARTING):
            return CommandResult(
                success=False,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                status="REJECTED",
                message=f"Orchestrator is in state '{self._state.value}' and cannot process commands.",
                error_code="ORCHESTRATOR_NOT_RUNNING",
                error_message=f"Orchestrator is {self._state.value}.",
            )

        with self._lock:
            # Check idempotency cache
            cache_key = command.idempotency_key or command.command_id
            if cache_key in self._active_operations:
                self.logger.info(f"Returning cached result for command ID/key '{cache_key}'")
                return self._active_operations[cache_key]

            self.audit_logger.log_event(
                component="Orchestrator",
                action=f"COMMAND_{command.command_type.upper()}",
                result="RECEIVED",
                correlation_id=command.correlation_id,
                details={"command_id": command.command_id, "payload": command.payload},
            )

            try:
                result = self._dispatch_command(command)
            except TaskNotFoundError as ex:
                result = CommandResult(
                    success=False,
                    command_id=command.command_id,
                    correlation_id=command.correlation_id,
                    status="FAILED",
                    message=str(ex),
                    error_code="TASK_NOT_FOUND",
                    error_message=str(ex),
                )
            except InvalidTaskTransitionError as ex:
                result = CommandResult(
                    success=False,
                    command_id=command.command_id,
                    correlation_id=command.correlation_id,
                    status="FAILED",
                    message=str(ex),
                    error_code="INVALID_TRANSITION",
                    error_message=str(ex),
                )
            except TaskValidationError as ex:
                result = CommandResult(
                    success=False,
                    command_id=command.command_id,
                    correlation_id=command.correlation_id,
                    status="REJECTED",
                    message=str(ex),
                    error_code="VALIDATION_FAILED",
                    error_message=str(ex),
                )
            except Exception as ex:
                result = CommandResult(
                    success=False,
                    command_id=command.command_id,
                    correlation_id=command.correlation_id,
                    status="FAILED",
                    message=f"Command execution error: {str(ex)}",
                    error_code="COMMAND_EXECUTION_ERROR",
                    error_message=str(ex),
                )

            # Store in active operations and history
            self._active_operations[cache_key] = result
            self._command_history.append(result)

            self.audit_logger.log_event(
                component="Orchestrator",
                action=f"COMMAND_{command.command_type.upper()}",
                result="SUCCESS" if result.success else "FAILED",
                task_id=result.task_id,
                correlation_id=command.correlation_id,
                error=result.error_message,
                details={"status": result.status},
            )

            return result

    def _dispatch_command(self, command: Command) -> CommandResult:
        """Route command to appropriate service execution method."""
        ctype = command.command_type

        if ctype == "CreateTask":
            title = command.payload.get("title") or getattr(command, "title", None)
            description = command.payload.get("description") or getattr(command, "description", None)
            raw_priority = command.payload.get("priority") or getattr(command, "priority", TaskPriority.MEDIUM)
            priority: TaskPriority = raw_priority if isinstance(raw_priority, TaskPriority) else TaskPriority.MEDIUM
            raw_owner = command.payload.get("owner") or getattr(command, "owner", "USER")
            owner: str = str(raw_owner) if raw_owner else "USER"
            parent_task_id = command.payload.get("parent_task_id") or getattr(command, "parent_task_id", None)
            metadata = command.payload.get("metadata") or getattr(command, "metadata", {})

            task = self.task_manager.create_task(
                title=title,
                description=description,
                priority=priority,
                owner=owner,
                correlation_id=command.correlation_id,
                parent_task_id=parent_task_id,
                metadata=metadata,
            )
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Task '{task.task_id}' created successfully.",
                data=task.model_dump(),
            )

        elif ctype == "StartTask":
            task_id = command.payload.get("task_id") or getattr(command, "task_id", None)
            if not task_id:
                raise InvalidCommandError("StartTaskCommand requires a valid 'task_id'.")
            task = self.task_manager.transition_task(task_id, TaskStatus.RUNNING, reason="Started by Orchestrator command")
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Task '{task.task_id}' transitioned to RUNNING.",
                data=task.model_dump(),
            )

        elif ctype == "PauseTask":
            task_id = command.payload.get("task_id") or getattr(command, "task_id", None)
            raw_reason = command.payload.get("reason") or getattr(command, "reason", "Paused by command")
            pause_reason: str = str(raw_reason) if raw_reason else "Paused by command"
            if not task_id:
                raise InvalidCommandError("PauseTaskCommand requires a valid 'task_id'.")
            task = self.task_manager.pause_task(task_id, reason=pause_reason)
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Task '{task.task_id}' PAUSED.",
                data=task.model_dump(),
            )

        elif ctype == "ResumeTask":
            task_id = command.payload.get("task_id") or getattr(command, "task_id", None)
            if not task_id:
                raise InvalidCommandError("ResumeTaskCommand requires a valid 'task_id'.")
            task = self.task_manager.resume_task(task_id)
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Task '{task.task_id}' RESUMED.",
                data=task.model_dump(),
            )

        elif ctype == "CancelTask":
            task_id = command.payload.get("task_id") or getattr(command, "task_id", None)
            raw_reason = command.payload.get("reason") or getattr(command, "reason", "Cancelled by command")
            cancel_reason: str = str(raw_reason) if raw_reason else "Cancelled by command"
            if not task_id:
                raise InvalidCommandError("CancelTaskCommand requires a valid 'task_id'.")
            task = self.task_manager.cancel_task(task_id, reason=cancel_reason)
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Task '{task.task_id}' CANCELLED.",
                data=task.model_dump(),
            )

        elif ctype == "GetTask":
            task_id = command.payload.get("task_id") or getattr(command, "task_id", None)
            if not task_id:
                raise InvalidCommandError("GetTaskCommand requires a valid 'task_id'.")
            task = self.task_manager.get_task(task_id)
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                task_id=task.task_id,
                status=task.status.value,
                message=f"Retrieved task '{task.task_id}'.",
                data=task.model_dump(),
            )

        elif ctype == "ListTasks":
            raw_status = command.payload.get("status") or getattr(command, "status", None)
            status_val: Optional[TaskStatus] = raw_status if isinstance(raw_status, TaskStatus) else None
            raw_prio = command.payload.get("priority") or getattr(command, "priority", None)
            priority_val: Optional[TaskPriority] = raw_prio if isinstance(raw_prio, TaskPriority) else None
            raw_owner = command.payload.get("owner") or getattr(command, "owner", None)
            owner_val: Optional[str] = str(raw_owner) if raw_owner else None
            raw_limit = command.payload.get("limit") or getattr(command, "limit", 100)
            raw_offset = command.payload.get("offset") or getattr(command, "offset", 0)
            limit_val: int = int(raw_limit) if raw_limit is not None else 100
            offset_val: int = int(raw_offset) if raw_offset is not None else 0

            tasks = self.task_manager.list_tasks(status=status_val, priority=priority_val, owner=owner_val, limit=limit_val, offset=offset_val)
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                status="SUCCESS",
                message=f"Retrieved {len(tasks)} tasks.",
                data={"tasks": [t.model_dump() for t in tasks], "count": len(tasks)},
            )

        elif ctype == "ShutdownApplication":
            reason = command.payload.get("reason") or getattr(command, "reason", "Shutdown requested")
            if self._context:
                self._context.cancellation_event.set()
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                status="SHUTDOWN_INITIATED",
                message=f"Application shutdown initiated: {reason}",
                data={"reason": reason},
            )

        elif ctype == "GetRuntimeStatus":
            status_data = {
                "orchestrator_state": self._state.value,
                "active_operations_count": len(self._active_operations),
                "task_manager_state": self.task_manager.state.value if self.task_manager else "UNKNOWN",
                "event_bus_state": self.event_bus.state.value if self.event_bus else "UNKNOWN",
            }
            return CommandResult(
                success=True,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                status="SUCCESS",
                message="Runtime status retrieved.",
                data=status_data,
            )

        else:
            raise InvalidCommandError(f"Unrecognized command type '{ctype}'.")

    def process_request(
        self,
        request_text: str,
        user_approved: bool = False,
        execution_handler: Optional[Callable[[Dict[str, Any], RollbackManager], Any]] = None,
        postcondition_verifier: Optional[Callable[[Any], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Backwards-compatible execution handler for legacy pipeline tests.
        """
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
            mem_health = ResourceMonitor.check_memory_health()
            if not mem_health["healthy"]:
                raise RuntimeError(mem_health["message"])

            self.task_manager.update_state(task_id, "PLANNING")
            understanding = self.llm_router.route_and_generate(
                prompt=f"Understand request: {request_text}",
                system_instruction="Analyze request requirements and determine parameters.",
            )

            context_memories = self.memory_engine.retrieve_memory(query=request_text)
            plan = {
                "steps": [{"action": "EXECUTE_TASK_LOGIC", "target": request_text}],
                "context": context_memories,
                "understanding": understanding["text"],
            }

            action_type = ActionType.MODIFY if "modify" in request_text.lower() or "update" in request_text.lower() else ActionType.CREATE
            action_req = ActionRequest(
                action_type=action_type,
                target=request_text,
                risk_level=RiskLevel.MEDIUM,
                user_approved=user_approved,
            )
            policy_decision = self.policy_engine.evaluate(action_req)

            if not policy_decision.allowed:
                self.task_manager.update_state(task_id, "FAILED", error=policy_decision.reason, verification_state="POLICY_DENIED")
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

            self.task_manager.update_state(task_id, "EXECUTING")
            agent_id = "legacy-agent-001"
            if self.agent_manager:
                temp_agent = self.agent_manager.spawn_agent(role="ExecutionSubagent", task_id=task_id, memory_limit_mb=1024)
                agent_id = temp_agent.config.agent_id

            self.audit_logger.log_event(
                component="Orchestrator",
                action="SPAWN_AGENT",
                result="SUCCESS",
                task_id=task_id,
                correlation_id=correlation_id,
                agent_id=agent_id,
            )

            def _runner():
                if execution_handler:
                    return execution_handler(plan, rollback_mgr)
                return f"Default execution output for: {request_text}"

            execution_output = _runner()

            self.task_manager.update_state(task_id, "VERIFYING")
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

            self.memory_engine.store_memory(key=f"task-{task_id}", content=f"Request: {request_text} | Result: {str(execution_output)[:100]}")
            self.task_manager.update_state(task_id, "COMPLETED", result=execution_output, verification_state="VERIFIED")

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
            self.audit_logger.log_event(
                component="Orchestrator",
                action="EXECUTION_FAILED",
                result="INITIATING_ROLLBACK",
                task_id=task_id,
                correlation_id=correlation_id,
                error=err_msg,
            )
            rollback_res = rollback_mgr.execute_rollback()
            self.task_manager.update_state(task_id, "FAILED", error=err_msg, verification_state="ROLLED_BACK")

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

    async def health(self) -> HealthStatusContract:
        """Query Orchestrator health status."""
        status = HealthState.HEALTHY if self._state == RuntimeState.RUNNING else HealthState.OFFLINE
        if self.task_manager and self.task_manager.state != RuntimeState.RUNNING:
            status = HealthState.DEGRADED
        return HealthStatusContract(
            component=self.name,
            status=status,
            metadata={
                "state": self._state.value,
                "active_operations_count": len(self._active_operations),
            },
        )
