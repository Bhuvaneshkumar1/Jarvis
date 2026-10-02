"""
Unit & Integration Tests for Central DatabaseManager & Connection Factory (Batch 16).
"""

import os
import pytest
import tempfile
import asyncio

from jarvis.core.runtime.context import RuntimeContext
from jarvis.database import (
    DatabaseManager,
    DatabaseSettings,
    DatabaseState,
    connection_scope,
    DatabaseUnavailableError,
)


@pytest.fixture
def temp_db_settings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_jarvis.db")
        backup_dir = os.path.join(tmp_dir, "backups")
        yield DatabaseSettings(db_path=db_path, backup_dir=backup_dir)


def test_database_settings_path_resolution(temp_db_settings):
    assert os.path.isabs(temp_db_settings.resolve_db_path())
    assert os.path.isabs(temp_db_settings.resolve_backup_dir())


def test_sqlite_connection_factory_and_pragma_settings(temp_db_settings):
    with connection_scope(temp_db_settings) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        assert cursor.fetchone()[0] == 1

        cursor.execute("PRAGMA journal_mode;")
        assert cursor.fetchone()[0].lower() == "wal"


@pytest.mark.asyncio
async def test_database_manager_lifecycle(temp_db_settings):
    mgr = DatabaseManager(settings=temp_db_settings)
    ctx = RuntimeContext(environment="testing")

    assert mgr.db_state == DatabaseState.UNINITIALIZED

    await mgr.initialize(ctx)
    assert mgr.db_state == DatabaseState.INITIALIZING

    await mgr.start()
    assert mgr.db_state == DatabaseState.READY

    health = await mgr.health()
    assert health.status.value == "HEALTHY"
    assert health.metadata["db_state"] == "READY"

    await mgr.stop()
    assert mgr.db_state == DatabaseState.CLOSED

    # Connection on closed database MUST raise DatabaseUnavailableError
    with pytest.raises(DatabaseUnavailableError):
        with mgr.connection():
            pass


def test_database_manager_table_creation(temp_db_settings):
    mgr = DatabaseManager(settings=temp_db_settings)
    asyncio.run(mgr.initialize(RuntimeContext(environment="testing")))
    asyncio.run(mgr.start())

    with mgr.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "schema_migrations",
            "app_metadata",
            "principals",
            "security_sessions",
            "policy_references",
            "tasks",
            "task_dependencies",
            "task_history",
            "approvals",
            "scoped_approvals",
        }
        assert required_tables.issubset(tables)

    asyncio.run(mgr.stop())
