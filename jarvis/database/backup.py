"""
Online Backup Engine & Restore Validator for JARVIS SQLite Database (Batch 16).
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.connection import connection_scope
from jarvis.database.exceptions import BackupError, RestoreValidationError


class DatabaseBackupManager:
    """
    Manages online SQLite backups using the SQLite Backup API and validates backup candidate integrity.
    """

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        self.settings = settings or get_database_settings()

    def create_backup(self, custom_filename: Optional[str] = None) -> str:
        """
        Creates a consistent online SQLite backup file using conn.backup().
        Validates the backup file with PRAGMA integrity_check post-creation.
        Returns the absolute path to the created backup file.
        """
        backup_dir = self.settings.resolve_backup_dir()
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            raise BackupError(f"Failed to create backup directory '{backup_dir}': {str(e)}") from e

        if custom_filename:
            filename = custom_filename
        else:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{now_str}_jarvis_backup.db"

        target_path = os.path.join(backup_dir, filename)

        try:
            with connection_scope(self.settings) as source_conn:
                dest_conn = sqlite3.connect(target_path)
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()

            # Post-backup integrity validation
            val_conn = sqlite3.connect(target_path)
            try:
                cursor = val_conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                res = cursor.fetchone()
                if not res or res[0] != "ok":
                    raise BackupError(f"Post-backup integrity check failed for '{target_path}': {res[0] if res else 'Unknown'}")
            finally:
                val_conn.close()

            return target_path

        except Exception as e:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            raise BackupError(f"Failed to create database backup: {str(e)}") from e

    def validate_restore_candidate(self, candidate_path: str) -> bool:
        """
        Validate a backup file candidate before allowing it to replace the active database.
        Checks existence, non-empty file size, SQLite header, and PRAGMA integrity_check.
        """
        abs_path = os.path.realpath(candidate_path)
        if not os.path.exists(abs_path):
            raise RestoreValidationError(f"Backup file '{abs_path}' does not exist.")

        if os.path.getsize(abs_path) == 0:
            raise RestoreValidationError(f"Backup file '{abs_path}' is empty (0 bytes).")

        try:
            conn = sqlite3.connect(abs_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                res = cursor.fetchone()
                if not res or res[0] != "ok":
                    raise RestoreValidationError(f"Backup candidate '{abs_path}' corrupted: {res[0] if res else 'Unknown'}")

                cursor.execute("SELECT COUNT(*) FROM schema_migrations;")
                cursor.fetchone()
                return True
            finally:
                conn.close()
        except Exception as e:
            raise RestoreValidationError(f"Candidate restore validation failed for '{abs_path}': {str(e)}") from e
