"""
Performance Throughput Benchmark for JARVIS Task Manager & SQLite Persistence (Batch 6).
"""

import os
import pytest
import tempfile
import time
from jarvis.core.enums import TaskStatus
from jarvis.core.tasks import TaskManager, TaskRepository


@pytest.mark.asyncio
async def test_task_manager_performance_benchmark():
    """
    Measures task creation, state transitions, retrieval, and listing throughput on SQLite persistence.
    """
    fd, temp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        repo = TaskRepository(db_path=temp_db)
        tm = TaskManager(repository=repo)
        await tm.start()

        num_tasks = 200

        # 1. Benchmark Task Creation
        start_create = time.perf_counter()
        created_ids = []
        for i in range(num_tasks):
            t = await tm.create_task(title=f"Benchmark Task {i}", metadata={"index": i})
            created_ids.append(t.task_id)
        elapsed_create = round(time.perf_counter() - start_create, 4)
        throughput_create = round(num_tasks / elapsed_create, 2) if elapsed_create > 0 else 0.0

        # 2. Benchmark State Transitions (READY -> RUNNING -> COMPLETED)
        start_trans = time.perf_counter()
        for tid in created_ids:
            await tm.transition_task(tid, TaskStatus.RUNNING)
            await tm.transition_task(tid, TaskStatus.COMPLETED)
        elapsed_trans = round(time.perf_counter() - start_trans, 4)
        throughput_trans = round((num_tasks * 2) / elapsed_trans, 2) if elapsed_trans > 0 else 0.0

        # 3. Benchmark Task Retrieval & Query Listing
        start_query = time.perf_counter()
        for tid in created_ids:
            await tm.get_task(tid)
        listed = await tm.list_tasks(status=TaskStatus.COMPLETED, limit=500)
        elapsed_query = round(time.perf_counter() - start_query, 4)
        throughput_query = round(num_tasks / elapsed_query, 2) if elapsed_query > 0 else 0.0

        await tm.stop()

        print("\n==================================================")
        print("       JARVIS TASK MANAGER PERFORMANCE BENCHMARK  ")
        print("==================================================")
        print(f"Tasks Created:            {num_tasks} in {elapsed_create}s ({throughput_create} tasks/sec)")
        print(f"State Transitions:        {num_tasks * 2} in {elapsed_trans}s ({throughput_trans} trans/sec)")
        print(f"Task Queries & Listing:   {len(listed)} fetched in {elapsed_query}s ({throughput_query} queries/sec)")
        print("==================================================")

        assert len(created_ids) == num_tasks
        assert len(listed) == num_tasks

    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except OSError:
                pass
