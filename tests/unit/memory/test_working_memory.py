"""
Unit Tests for Working Memory Subsystem (Batch 25).
Tests data models, validation, repository CRUD, prioritizer, retrieval engine, token budgeting, and expiration.
"""

import time
import pytest
from jarvis.core.enums import MemoryScope, SecurityLevel
from jarvis.database.connection import connection_scope
from jarvis.database.migrations.runner import MigrationRunner
from jarvis.memory.working import (
    WorkingMemoryEntry,
    WorkingMemoryManager,
    MemoryRetrievalFilter,
    MemoryPrioritizer,
    TokenBudgetManager,
    MemoryStatus,
    MemoryAccessDeniedError,
    MemoryConcurrencyError,
)


@pytest.fixture(autouse=True)
def init_in_memory_db():
    """Applies database migrations and clears working_memories table before each test."""
    with connection_scope() as conn:
        runner = MigrationRunner()
        runner.discover_and_apply_pending(conn)
        conn.execute("DELETE FROM working_memories;")
        conn.commit()


def test_working_memory_entry_validation():
    """Test data model validations on WorkingMemoryEntry."""
    # Valid entry creation
    entry = WorkingMemoryEntry(
        scope=MemoryScope.CONVERSATION,
        owner_id="user_1",
        conversation_id="conv_1",
        content="Important context line",
        priority=7,
    )
    assert entry.memory_id.startswith("wmem-")
    assert entry.status == MemoryStatus.ACTIVE

    # Empty owner validation
    with pytest.raises(ValueError):
        WorkingMemoryEntry(scope=MemoryScope.WORKING, owner_id="", content="test")

    # Empty content validation
    with pytest.raises(ValueError):
        WorkingMemoryEntry(scope=MemoryScope.WORKING, owner_id="user_1", content="   ")

    # Expiration before creation timestamp validation
    with pytest.raises(ValueError):
        WorkingMemoryEntry(
            scope=MemoryScope.WORKING,
            owner_id="user_1",
            content="test",
            created_at=100.0,
            expires_at=50.0,
        )


def test_secret_redaction_in_memory_content():
    """Test that sensitive API keys are automatically redacted in content and metadata."""
    secret_key = "sk-1234567890abcdef1234567890abcdef"
    entry = WorkingMemoryEntry(
        scope=MemoryScope.WORKING,
        owner_id="user_1",
        content=f"User secret key is {secret_key}",
        metadata={"token": secret_key},
    )
    assert secret_key not in entry.content
    assert "[REDACTED" in entry.content


def test_working_memory_crud_operations():
    """Test WorkingMemoryManager CRUD lifecycle."""
    manager = WorkingMemoryManager()

    # 1. Create
    entry = WorkingMemoryEntry(
        scope=MemoryScope.TASK,
        owner_id="user_abc",
        task_id="task_100",
        content="Task state checkpoint",
        priority=8,
    )
    created = manager.create(entry)
    assert created.memory_id == entry.memory_id

    # 2. Read
    fetched = manager.get(created.memory_id, requester_owner_id="user_abc")
    assert fetched is not None
    assert fetched.content == "Task state checkpoint"

    # 3. Read Access Denied
    with pytest.raises(MemoryAccessDeniedError):
        manager.get(created.memory_id, requester_owner_id="unauthorized_user")

    # 4. Update
    fetched.content = "Updated task state checkpoint"
    updated = manager.update(fetched, requester_owner_id="user_abc")
    assert updated.version == 2
    assert updated.content == "Updated task state checkpoint"

    # 5. Concurrency Control Check
    stale_entry = fetched.model_copy()
    stale_entry.content = "Stale update attempt"
    with pytest.raises(MemoryConcurrencyError):
        manager.update(stale_entry, requester_owner_id="user_abc")

    # 6. Delete
    deleted = manager.delete(created.memory_id, requester_owner_id="user_abc")
    assert deleted is True
    assert manager.get(created.memory_id, requester_owner_id="user_abc") is None


def test_scope_isolation_and_clearing():
    """Test clearing memory scope by owner."""
    manager = WorkingMemoryManager()

    # Create 3 memories across scopes
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.CONVERSATION,
            owner_id="user_x",
            conversation_id="c1",
            content="Conv memory 1",
        )
    )
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.CONVERSATION,
            owner_id="user_x",
            conversation_id="c1",
            content="Conv memory 2",
        )
    )
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.TASK,
            owner_id="user_x",
            task_id="t1",
            content="Task memory 1",
        )
    )

    # Clear conversation scope for user_x
    cleared = manager.clear_scope(
        scope=MemoryScope.CONVERSATION,
        owner_id="user_x",
        conversation_id="c1",
    )
    assert cleared == 2

    # Task memory should remain active
    task_mems = manager.list_by_scope(
        scope=MemoryScope.TASK,
        owner_id="user_x",
        task_id="t1",
    )
    assert len(task_mems) == 1


def test_prioritizer_and_selective_retrieval():
    """Test memory prioritizer scoring, classification filtering, and tie-breaking."""
    prioritizer = MemoryPrioritizer()
    now = time.time()

    high_pri = WorkingMemoryEntry(
        scope=MemoryScope.CONVERSATION,
        owner_id="u1",
        content="High priority Python coding memory",
        priority=9,
        classification=SecurityLevel.INTERNAL,
        created_at=now - 100,
    )
    low_pri = WorkingMemoryEntry(
        scope=MemoryScope.CONVERSATION,
        owner_id="u1",
        content="Low priority general chatter",
        priority=2,
        classification=SecurityLevel.INTERNAL,
        created_at=now - 50,
    )
    confidential = WorkingMemoryEntry(
        scope=MemoryScope.CONVERSATION,
        owner_id="u1",
        content="Confidential financial note",
        priority=10,
        classification=SecurityLevel.CONFIDENTIAL,
        created_at=now,
    )

    filter_internal = MemoryRetrievalFilter(
        owner_id="u1",
        max_classification=SecurityLevel.INTERNAL,
        query="Python coding",
    )

    # Confidential should be hard-filtered out
    ranked = prioritizer.rank_memories([high_pri, low_pri, confidential], filter_internal, now=now)
    assert len(ranked) == 2
    assert ranked[0][0].memory_id == high_pri.memory_id


def test_token_budget_manager():
    """Test token estimation and context fitting."""
    budget_mgr = TokenBudgetManager()

    entries = [
        WorkingMemoryEntry(scope=MemoryScope.WORKING, owner_id="u1", content="A" * 100, priority=9),
        WorkingMemoryEntry(scope=MemoryScope.WORKING, owner_id="u1", content="B" * 200, priority=7),
        WorkingMemoryEntry(scope=MemoryScope.WORKING, owner_id="u1", content="C" * 300, priority=5),
    ]

    # Fit within generous budget
    selected, omitted, total_tokens = budget_mgr.fit_to_budget(entries, max_tokens=1000)
    assert len(selected) == 3
    assert len(omitted) == 0

    # Fit within restricted budget
    selected, omitted, total_tokens = budget_mgr.fit_to_budget(entries, max_tokens=80)
    assert len(selected) >= 1
    assert len(omitted) >= 1


def test_memory_expiration_manager():
    """Test timestamp expiration and retention cleanup."""
    manager = WorkingMemoryManager()
    now = time.time()

    # Create memory expiring in 10 seconds
    expiring = manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.WORKING,
            owner_id="u1",
            content="Temporary pin code",
            created_at=now,
            expires_at=now + 10,
        )
    )

    # Expire sweep in future (now + 20)
    expired_cnt = manager.expire(now=now + 20)
    assert expired_cnt >= 1

    # Retrieval in future (now + 20) should exclude expired memory
    filter_req = MemoryRetrievalFilter(owner_id="u1")
    results = manager.retrieval_engine.retrieve(manager.repository, filter_req, now=now + 20)
    assert not any(m.memory_id == expiring.memory_id for m in results)
