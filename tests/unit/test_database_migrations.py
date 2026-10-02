"""
Unit & Integration Tests for Versioned Migration Engine (Batch 16).
"""

import os
import pytest
import tempfile

from jarvis.database import (
    DatabaseSettings,
    MigrationRunner,
    connection_scope,
    MigrationChecksumError,
)


@pytest.fixture
def temp_db_settings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "migration_test.db")
        yield DatabaseSettings(db_path=db_path)


def test_migration_runner_initial_schema_execution(temp_db_settings):
    runner = MigrationRunner(settings=temp_db_settings)
    with connection_scope(temp_db_settings) as conn:
        applied = runner.discover_and_apply_pending(conn)
        assert len(applied) == 2
        assert "001_initial_core_schema" in applied
        assert "002_task_persistence_enhancements" in applied

        # Re-running discovery is idempotent
        re_applied = runner.discover_and_apply_pending(conn)
        assert len(re_applied) == 2


def test_migration_checksum_tamper_detection(temp_db_settings):
    runner = MigrationRunner(settings=temp_db_settings)

    with connection_scope(temp_db_settings) as conn:
        runner.discover_and_apply_pending(conn)

        # Tamper with recorded checksum in database
        conn.execute("UPDATE schema_migrations SET checksum = 'corrupted_hash' WHERE version = 1;")
        conn.commit()

        # Re-running migration engine MUST detect checksum tampering
        with pytest.raises(MigrationChecksumError):
            runner.discover_and_apply_pending(conn)
