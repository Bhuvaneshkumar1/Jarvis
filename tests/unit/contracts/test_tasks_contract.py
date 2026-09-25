import pytest
from jarvis.core.contracts.tasks import TaskContract, TaskStepContract
from jarvis.core.enums import TaskStatus, TaskPriority

def test_task_contract_serialization():
    task = TaskContract(
        description="Execute batch 2 contract verification",
        priority=TaskPriority.HIGH,
        status=TaskStatus.PLANNED,
    )
    assert task.task_id.startswith("task-")

    json_str = task.model_dump_json()
    reconstructed = TaskContract.model_validate_json(json_str)
    assert reconstructed.priority == TaskPriority.HIGH
    assert reconstructed.status == TaskStatus.PLANNED

def test_task_step_contract_dependencies():
    step1 = TaskStepContract(task_id="task-100", sequence=1, description="Inspect repository")
    step2 = TaskStepContract(task_id="task-100", sequence=2, description="Run tests", dependencies=[step1.step_id])

    assert step2.dependencies[0] == step1.step_id
    assert step2.sequence == 2

def test_negative_invalid_retry_count():
    with pytest.raises(ValueError):
        TaskContract(description="Valid task", retry_count=-1)
