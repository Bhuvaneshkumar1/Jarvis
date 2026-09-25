from jarvis.core.agent_manager import AgentManager, AgentStatus

def test_spawn_and_list_agents():
    mgr = AgentManager()
    agent = mgr.spawn_agent(role="TestRole", task_id="task-123")
    assert agent.config.role == "TestRole"
    assert agent.config.task_id == "task-123"

    agents_list = mgr.list_agents()
    assert len(agents_list) == 1
    assert agents_list[0]["agent_id"] == agent.config.agent_id

    mgr.terminate_agent(agent.config.agent_id)
    assert len(mgr.list_agents()) == 0

def test_agent_execution_success():
    mgr = AgentManager()
    agent = mgr.spawn_agent(role="Worker", task_id="task-999")
    result = agent.execute_task(lambda x: x * 2, 21)
    assert result == 42
    assert agent.status == AgentStatus.COMPLETED
