"""
Throughput and Latency Performance Tests for JARVIS Orchestrator (Batch 7).
"""

import os
import pytest
import tempfile
import time
from jarvis.core.tasks import TaskManager, TaskRepository
from jarvis.core.orchestration import (
    Orchestrator,
    CreateTaskCommand,
    GetTaskCommand,
)


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_orchestrator_throughput_benchmark(temp_db_path):
    repo = TaskRepository(db_path=temp_db_path)
    tm = TaskManager(repository=repo)
    orchestrator = Orchestrator(task_manager=tm)
    await tm.start()
    await orchestrator.start()

    num_operations = 200
    start_time = time.time()

    task_ids = []
    for i in range(num_operations):
        cmd = CreateTaskCommand(title=f"Benchmark Task {i}", metadata={"idx": i})
        res = orchestrator.execute_command(cmd)
        task_ids.append(res.task_id)

    creation_time = time.time() - start_time

    query_start = time.time()
    for tid in task_ids[:100]:
        orchestrator.execute_command(GetTaskCommand(task_id=tid))

    query_time = time.time() - query_start

    print(
        f"\n[ORCHESTRATOR BENCHMARK] {num_operations} command executions completed in {creation_time:.4f}s "
        f"({num_operations / creation_time:.2f} ops/sec). "
        f"100 queries completed in {query_time:.4f}s ({100 / query_time:.2f} queries/sec)."
    )

    assert creation_time < 25.0
    assert query_time < 10.0

    await orchestrator.stop()
    await tm.stop()
