"""
Concurrency & Security Authorization Tests for Task Subsystem (Batch 17).
"""

import os
import pytest
import tempfile
import threading
import time

from jarvis.core.enums import TaskStatus
from jarvis.core.tasks import TaskManager, TaskVersionConflictError, TaskAuthorizationError
from jarvis.security.policy import PolicyEngine, Principal, PrincipalType


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield os.path.join(tmp_dir, "task_concurrency.db")


def test_optimistic_concurrency_version_conflict(temp_db_path):
    mgr = TaskManager(db_path=temp_db_path)
    task = mgr.create_task(title="Concurrent Task")

    # Read version
    t_reader1 = mgr.get_task(task.task_id)
    init_version = t_reader1.version

    # First update succeeds
    mgr.transition_task(task.task_id, TaskStatus.QUEUED, reason="First update", expected_version=init_version)

    # Second stale update attempting to use initial version MUST FAIL
    with pytest.raises(TaskVersionConflictError):
        mgr.transition_task(task.task_id, TaskStatus.READY, reason="Stale update", expected_version=init_version)


def test_concurrent_task_updates(temp_db_path):
    mgr = TaskManager(db_path=temp_db_path)
    task = mgr.create_task(title="Multi-Threaded Update Task")
    mgr.transition_task(task.task_id, TaskStatus.QUEUED, reason="Queued")
    mgr.transition_task(task.task_id, TaskStatus.READY, reason="Ready")
    mgr.transition_task(task.task_id, TaskStatus.RUNNING, reason="Started")

    errors = []

    def update_task_worker(worker_id):
        try:
            for _ in range(5):
                t = mgr.get_task(task.task_id)
                # Attempt update
                t.metadata[f"worker_{worker_id}"] = time.time()
                try:
                    mgr.repository.update_task(t, expected_version=t.version)
                except TaskVersionConflictError:
                    pass  # Conflict expected in multi-threaded environment
                time.sleep(0.002)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=update_task_worker, args=(i,)) for i in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors
    final_task = mgr.get_task(task.task_id)
    assert final_task.version > 1


def test_unauthorized_task_mutation_rejection(temp_db_path):
    policy_eng = PolicyEngine()
    mgr = TaskManager(db_path=temp_db_path, policy_engine=policy_eng)

    unauthorized_principal = Principal(
        principal_id="unauth_agent",
        principal_type=PrincipalType.AGENT,
        permissions=[],  # Lacks permissions
    )

    # Creation with unauthorized principal MUST raise TaskAuthorizationError
    with pytest.raises(TaskAuthorizationError):
        mgr.create_task(title="Unauthorized Task", principal=unauthorized_principal)
