import uuid
import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class TaskState(str):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"

class TaskRecord(BaseModel):
    task_id: str
    description: str
    state: str = TaskState.CREATED
    correlation_id: str
    created_at: float
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    verification_state: str = "UNVERIFIED"

class TaskManager:
    """
    Persistent Task Lifecycle Manager.
    Enforces task state tracking and history.
    """

    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}

    def create_task(self, description: str, correlation_id: Optional[str] = None) -> TaskRecord:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        cid = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
        record = TaskRecord(
            task_id=task_id,
            description=description,
            correlation_id=cid,
            created_at=time.time(),
        )
        self._tasks[task_id] = record
        return record

    def update_state(
        self,
        task_id: str,
        state: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        verification_state: str = "UNVERIFIED",
    ) -> TaskRecord:
        if task_id not in self._tasks:
            raise KeyError(f"Task ID '{task_id}' not found.")
        record = self._tasks[task_id]
        record.state = state
        if result is not None:
            record.result = result
        if error is not None:
            record.error = error
        record.verification_state = verification_state
        if state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.ROLLED_BACK]:
            record.completed_at = time.time()
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)
