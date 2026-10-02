"""
Idempotency and Concurrency Tests for Recovery Subsystem (Batch 19).
"""

import pytest
from jarvis.core.recovery.models import RecoveryStatus
from jarvis.core.recovery.coordinator import RecoveryCoordinator
from jarvis.core.recovery.store import RecoveryRepository
from jarvis.core.exceptions import RecoveryLockError


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_recovery_idempotency_concurrency.db")


def test_repeated_recovery_idempotency(temp_db_path):
    coordinator = RecoveryCoordinator(db_path=temp_db_path)

    # First recovery run
    rec1 = coordinator.execute_recovery()
    assert rec1.status == RecoveryStatus.COMPLETED

    # Second recovery run (idempotent)
    rec2 = coordinator.execute_recovery()
    assert rec2.status == RecoveryStatus.COMPLETED
    assert rec2.recovered_count == 0  # 0 newly recovered records on second run


def test_concurrent_recovery_coordinators_lock_contention(temp_db_path):
    RecoveryCoordinator(db_path=temp_db_path, owner_id="owner_alpha")
    c2 = RecoveryCoordinator(db_path=temp_db_path, owner_id="owner_beta")

    # Manually hold lock with long TTL using owner_alpha
    repo = RecoveryRepository(db_path=temp_db_path)
    token = repo.acquire_recovery_lock(
        lock_name="system_startup_recovery",
        owner_id="owner_alpha",
        ttl_seconds=300.0,
    )
    assert token == 1

    # Attempting recovery with owner_beta must fail with RecoveryLockError
    with pytest.raises(RecoveryLockError, match="held by active owner 'owner_alpha'"):
        c2.execute_recovery()

    # Release lock
    repo.release_recovery_lock(lock_name="system_startup_recovery", owner_id="owner_alpha", fencing_token=token)

    # Now owner_beta can run recovery successfully
    rec2 = c2.execute_recovery()
    assert rec2.status == RecoveryStatus.COMPLETED
