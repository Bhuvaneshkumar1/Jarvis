"""
Integration Tests for Working Memory Subsystem (Batch 25).
Verifies database migration 005, transactional persistence, DatabaseManager integration, and agent memory isolation.
"""

import pytest
from jarvis.database.connection import connection_scope
from jarvis.database.migrations.runner import MigrationRunner
from jarvis.memory.working import (
    WorkingMemoryEntry,
    WorkingMemoryManager,
    MemoryRetrievalFilter,
    MemoryAccessDeniedError,
)
from jarvis.core.enums import MemoryScope


@pytest.fixture(autouse=True)
def setup_integration_db():
    """Applies migration 005 and clears working_memories table before each integration test."""
    with connection_scope() as conn:
        runner = MigrationRunner()
        runner.discover_and_apply_pending(conn)
        conn.execute("DELETE FROM working_memories;")
        conn.commit()


def test_working_memory_db_migration_and_persistence():
    """Verify database schema creation and transactional persistence."""
    with connection_scope() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='working_memories'")
        table = cursor.fetchone()
        assert table is not None

        cursor.execute("PRAGMA index_list('working_memories')")
        indexes = [row["name"] for row in cursor.fetchall()]
        assert "idx_working_memories_scope_owner" in indexes


def test_multi_agent_memory_isolation():
    """
    Verify that Agent A cannot access Agent B's working memory context.
    """
    manager = WorkingMemoryManager()

    # Agent A stores private working context
    agent_a_mem = manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.AGENT,
            owner_id="agent_alpha",
            agent_id="agent_alpha",
            content="Alpha secret task state",
            priority=8,
        )
    )

    # Agent B stores private working context
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.AGENT,
            owner_id="agent_beta",
            agent_id="agent_beta",
            content="Beta secret task state",
            priority=8,
        )
    )

    # Agent A retrieves memories
    alpha_results = manager.retrieve(
        MemoryRetrievalFilter(
            scopes=[MemoryScope.AGENT],
            owner_id="agent_alpha",
            agent_id="agent_alpha",
        )
    )
    assert len(alpha_results) == 1
    assert alpha_results[0].content == "Alpha secret task state"

    # Agent B retrieves memories
    beta_results = manager.retrieve(
        MemoryRetrievalFilter(
            scopes=[MemoryScope.AGENT],
            owner_id="agent_beta",
            agent_id="agent_beta",
        )
    )
    assert len(beta_results) == 1
    assert beta_results[0].content == "Beta secret task state"

    # Cross-agent unauthorized direct read attempt
    with pytest.raises(MemoryAccessDeniedError):
        manager.get(agent_a_mem.memory_id, requester_owner_id="agent_beta")


def test_working_memory_statistics_report():
    """Verify statistics calculation report."""
    manager = WorkingMemoryManager()
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.CONVERSATION,
            owner_id="user_stat",
            content="Stat conversation item",
        )
    )
    manager.create(
        WorkingMemoryEntry(
            scope=MemoryScope.TASK,
            owner_id="user_stat",
            content="Stat task item",
        )
    )

    stats = manager.get_statistics(owner_id="user_stat")
    assert stats.total_memories == 2
    assert stats.active_memories == 2
    assert "CONVERSATION" in stats.memories_by_scope
    assert "TASK" in stats.memories_by_scope
