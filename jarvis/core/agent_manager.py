import uuid
import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from jarvis.core.resource_monitor import ResourceMonitor

class AgentStatus(str):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"

class TemporaryAgentConfig(BaseModel):
    agent_id: str
    role: str
    task_id: str
    memory_limit_mb: int = 1024
    created_at: float

class TemporaryAgent:
    """
    Isolated Temporary Agent wrapper with lifecycle and resource limits.
    """

    def __init__(self, config: TemporaryAgentConfig):
        self.config = config
        self.status = AgentStatus.INITIALIZING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None

    def execute_task(self, task_fn, *args, **kwargs) -> Any:
        self.status = AgentStatus.RUNNING

        # Resource check before execution
        mem_info = ResourceMonitor.get_system_memory_info()
        if mem_info["process_rss_mb"] > ResourceMonitor.HARD_MAX_MB:
            self.status = AgentStatus.FAILED
            self.error = f"Agent failed to execute: System RAM budget exceeded hard max {ResourceMonitor.HARD_MAX_MB} MB."
            raise RuntimeError(self.error)

        try:
            res = task_fn(*args, **kwargs)
            self.result = res
            self.status = AgentStatus.COMPLETED
            return res
        except Exception as e:
            self.status = AgentStatus.FAILED
            self.error = str(e)
            raise e
        finally:
            self.terminate()

    def terminate(self):
        if self.status not in [AgentStatus.COMPLETED, AgentStatus.FAILED]:
            self.status = AgentStatus.TERMINATED

class AgentManager:
    """
    Dynamic Temporary Agent Spawner & Lifecycle Manager.
    Rule 9: Single authoritative agent manager implementation.
    """

    def __init__(self):
        self._active_agents: Dict[str, TemporaryAgent] = {}

    def spawn_agent(self, role: str, task_id: str, memory_limit_mb: int = 1024) -> TemporaryAgent:
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        config = TemporaryAgentConfig(
            agent_id=agent_id,
            role=role,
            task_id=task_id,
            memory_limit_mb=memory_limit_mb,
            created_at=time.time(),
        )
        agent = TemporaryAgent(config)
        self._active_agents[agent_id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Optional[TemporaryAgent]:
        return self._active_agents.get(agent_id)

    def terminate_agent(self, agent_id: str):
        agent = self._active_agents.get(agent_id)
        if agent:
            agent.terminate()
            del self._active_agents[agent_id]

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "agent_id": a.config.agent_id,
                "role": a.config.role,
                "task_id": a.config.task_id,
                "status": a.status,
            }
            for a in self._active_agents.values()
        ]
