"""
Database Health Check & SQLite Integrity Evaluator for JARVIS (Batch 16).
"""

import os
import sqlite3
import time
from typing import Dict, Any, Optional
from jarvis.core.enums import HealthState
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.connection import connection_scope
from jarvis.database.exceptions import IntegrityError


class DatabaseHealthCheck:
    """
    Evaluates database health, accessibility, WAL mode, pending migrations,
    and executes SQLite integrity & foreign key checks.
    """

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        self.settings = settings or get_database_settings()
        self.last_integrity_check: Optional[float] = None

    def run_integrity_check(self, conn: sqlite3.Connection) -> None:
        """
        Executes PRAGMA integrity_check and PRAGMA foreign_key_check.
        Raises IntegrityError if corruption or constraint errors are detected.
        """
        cursor = conn.cursor()

        # 1. Integrity check
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()
        if not res or res[0] != "ok":
            corruption_msg = res[0] if res else "Unknown corruption"
            raise IntegrityError(f"CRITICAL: SQLite integrity check failed: {corruption_msg}")

        # 2. Foreign key check
        cursor.execute("PRAGMA foreign_key_check;")
        fk_errors = cursor.fetchall()
        if fk_errors:
            raise IntegrityError(f"CRITICAL: Foreign key check failed with {len(fk_errors)} violation(s).")

        self.last_integrity_check = time.time()

    def check_health(self) -> HealthStatusContract:
        db_path = self.settings.resolve_db_path()
        details: Dict[str, Any] = {
            "db_path": db_path,
            "exists": os.path.exists(db_path),
            "last_integrity_check": self.last_integrity_check,
        }

        if db_path != ":memory:" and not os.path.exists(db_path):
            return HealthStatusContract(
                component="DatabaseSubsystem",
                status=HealthState.UNHEALTHY,
                error=f"Database file '{db_path}' does not exist.",
                metadata=details,
            )

        try:
            with connection_scope(self.settings) as conn:
                self.run_integrity_check(conn)

                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode;")
                j_mode = cursor.fetchone()[0]
                details["journal_mode"] = j_mode

                cursor.execute("SELECT COUNT(*) FROM schema_migrations;")
                mig_count = cursor.fetchone()[0]
                details["migration_count"] = mig_count

                return HealthStatusContract(
                    component="DatabaseSubsystem",
                    status=HealthState.HEALTHY,
                    error=None,
                    metadata=details,
                )
        except Exception as e:
            return HealthStatusContract(
                component="DatabaseSubsystem",
                status=HealthState.UNHEALTHY,
                error=f"Database health check failed: {str(e)}",
                metadata=details,
            )
