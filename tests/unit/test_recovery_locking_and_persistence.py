"""
Database Integration & Persistence Tests for Recovery Repository & Locking (Batch 19).
"""

import pytest
import time
from jarvis.core.recovery.models import RecoveryRecord, RecoveryStatus
from jarvis.core.recovery.store import RecoveryRepository
from jarvis.core.exceptions import RecoveryLockError


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_recovery_persistence.db")


@pytest.fixture
def repo(temp_db_path):
    return RecoveryRepository(db_path=temp_db_path)


def test_migration_004_and_lock_acquisition(repo):
    token1 = repo.acquire_recovery_lock(lock_name="test_lock", owner_id="owner_1", ttl_seconds=60.0)
    assert token1 == 1

    # Same owner renewing lock gets incremented token
    token2 = repo.acquire_recovery_lock(lock_name="test_lock", owner_id="owner_1", ttl_seconds=60.0)
    assert token2 == 2

    # Release lock
    released = repo.release_recovery_lock(lock_name="test_lock", owner_id="owner_1", fencing_token=token2)
    assert released is True


def test_lock_contention_and_abandoned_lock_takeover(temp_db_path):
    repo1 = RecoveryRepository(db_path=temp_db_path)
    repo2 = RecoveryRepository(db_path=temp_db_path)

    # Owner 1 acquires lock with short TTL
    t1 = repo1.acquire_recovery_lock(lock_name="lock_A", owner_id="owner_1", ttl_seconds=0.1)
    assert t1 == 1

    # Active lock blocks Owner 2
    with pytest.raises(RecoveryLockError):
        repo2.acquire_recovery_lock(lock_name="lock_A", owner_id="owner_2", ttl_seconds=60.0)

    # Wait for lock TTL to expire (abandoned lock takeover)
    time.sleep(0.15)

    # Owner 2 takes over expired lock with incremented fencing token
    t2 = repo2.acquire_recovery_lock(lock_name="lock_A", owner_id="owner_2", ttl_seconds=60.0)
    assert t2 == 2


def test_recovery_record_crud(repo):
    rec = RecoveryRecord(status=RecoveryStatus.INSPECTING, inspected_count=5)
    saved = repo.save_recovery_record(rec)
    assert saved.recovery_id == rec.recovery_id

    fetched = repo.get_recovery_record(rec.recovery_id)
    assert fetched is not None
    assert fetched.status == RecoveryStatus.INSPECTING
    assert fetched.inspected_count == 5

    # Update record
    fetched.status = RecoveryStatus.COMPLETED
    fetched.recovered_count = 5
    updated = repo.update_recovery_record(fetched)
    assert updated.status == RecoveryStatus.COMPLETED

    re_fetched = repo.get_recovery_record(rec.recovery_id)
    assert re_fetched.status == RecoveryStatus.COMPLETED
    assert re_fetched.recovered_count == 5


def test_outbox_queue_operations(repo):
    evt1 = repo.enqueue_outbox_event("TaskCompleted", {"task_id": "t-100"})
    evt2 = repo.enqueue_outbox_event("ApprovalGranted", {"approval_id": "a-200"})

    pending = repo.get_pending_outbox_events()
    assert len(pending) == 2

    # Mark evt1 dispatched
    repo.mark_outbox_dispatched(evt1.event_id)

    pending_after = repo.get_pending_outbox_events()
    assert len(pending_after) == 1
    assert pending_after[0].event_id == evt2.event_id

    # Mark evt2 failed
    repo.mark_outbox_failed(evt2.event_id, "Network timeout")
    # Event attempt_count becomes 1 < max_attempts 5, so remains PENDING for retry
    pending_retry = repo.get_pending_outbox_events()
    assert len(pending_retry) == 1
    assert pending_retry[0].attempt_count == 1
    assert pending_retry[0].last_error == "Network timeout"


def test_database_integrity_validation(repo):
    integrity = repo.validate_database_integrity()
    assert integrity["fatal_corruption"] is False
    assert integrity["orphaned_dependencies"] == 0
