"""
Unit & Integration Tests for Backup Engine & Maintenance Scripts (Batch 16).
"""

import os
import pytest
import tempfile

from jarvis.database import (
    DatabaseSettings,
    DatabaseBackupManager,
    connection_scope,
    compute_checksum,
    CORE_SCHEMA_DDL,
    RestoreValidationError,
)
from jarvis.database.scripts import migrate, check_db, backup_db


@pytest.fixture
def temp_db_settings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "backup_source.db")
        backup_dir = os.path.join(tmp_dir, "backups")
        settings = DatabaseSettings(db_path=db_path, backup_dir=backup_dir)

        # Seed source database with initial schema
        with connection_scope(settings) as conn:
            conn.executescript(CORE_SCHEMA_DDL)
            chk = compute_checksum(CORE_SCHEMA_DDL)
            conn.execute(
                """
                INSERT INTO schema_migrations (version, migration_id, checksum, applied_at, execution_status)
                VALUES (1, '001_initial_core_schema', ?, 1000.0, 'SUCCESS');
                """,
                (chk,),
            )
            conn.execute("INSERT INTO app_metadata (key, value, created_at, updated_at) VALUES ('version', '1.0.0', 1000.0, 1000.0);")
            conn.commit()

        yield settings


def test_online_backup_creation_and_integrity_validation(temp_db_settings):
    backup_mgr = DatabaseBackupManager(settings=temp_db_settings)

    backup_path = backup_mgr.create_backup(custom_filename="test_backup.db")
    assert os.path.exists(backup_path)
    assert os.path.getsize(backup_path) > 0

    # Verify candidate restore validation passes
    assert backup_mgr.validate_restore_candidate(backup_path)


def test_restore_validation_rejects_corrupted_file(temp_db_settings):
    backup_mgr = DatabaseBackupManager(settings=temp_db_settings)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_f:
        tmp_f.write(b"NOT_A_SQLITE_DATABASE_HEADER")
        corrupted_path = tmp_f.name

    try:
        with pytest.raises(RestoreValidationError):
            backup_mgr.validate_restore_candidate(corrupted_path)
    finally:
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)


def test_maintenance_scripts_execution(temp_db_settings, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_PATH", temp_db_settings.resolve_db_path())
    monkeypatch.setenv("JARVIS_BACKUP_DIR", temp_db_settings.resolve_backup_dir())

    # 1. check_db script
    ret_check = check_db.main()
    assert ret_check == 0

    # 2. migrate script
    ret_mig = migrate.main()
    assert ret_mig == 0

    # 3. backup_db script
    ret_back = backup_db.main()
    assert ret_back == 0
