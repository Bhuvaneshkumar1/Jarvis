"""
Versioned Transactional Migration Engine for JARVIS (Batch 16 & Batch 17).
Enforces SHA-256 checksum verification, deterministic version ordering, and atomic execution.
"""

import glob
import hashlib
import importlib.util
import os
import sqlite3
import time
from typing import List, Dict, Optional, Tuple
from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.schema import CORE_SCHEMA_DDL
from jarvis.database.exceptions import (
    MigrationError,
    MigrationChecksumError,
)


def compute_checksum(content: str) -> str:
    """Compute deterministic SHA-256 checksum of migration string content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


class MigrationRecord:
    def __init__(self, version: int, migration_id: str, checksum: str, applied_at: float, execution_status: str):
        self.version = version
        self.migration_id = migration_id
        self.checksum = checksum
        self.applied_at = applied_at
        self.execution_status = execution_status


class MigrationRunner:
    """
    Authoritative Migration Engine managing versioned database schema upgrades.
    """

    def __init__(self, settings: Optional[DatabaseSettings] = None):
        self.settings = settings or get_database_settings()

    def _ensure_migration_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                migration_id TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL,
                applied_at REAL NOT NULL,
                execution_status TEXT NOT NULL
            );
            """
        )
        conn.commit()

    def get_applied_migrations(self, conn: sqlite3.Connection) -> List[MigrationRecord]:
        self._ensure_migration_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT version, migration_id, checksum, applied_at, execution_status FROM schema_migrations ORDER BY version ASC")
        records = []
        for row in cursor.fetchall():
            records.append(
                MigrationRecord(
                    version=row["version"],
                    migration_id=row["migration_id"],
                    checksum=row["checksum"],
                    applied_at=row["applied_at"],
                    execution_status=row["execution_status"],
                )
            )
        return records

    def run_initial_schema(self, conn: sqlite3.Connection) -> None:
        """Run initial core DDL and record v1 baseline migration."""
        self._ensure_migration_table(conn)
        applied = self.get_applied_migrations(conn)
        applied_versions = {m.version for m in applied}

        if 1 in applied_versions:
            return

        checksum = compute_checksum(CORE_SCHEMA_DDL)
        now = time.time()

        with conn:
            conn.executescript(CORE_SCHEMA_DDL)
            conn.execute(
                """
                INSERT INTO schema_migrations (version, migration_id, checksum, applied_at, execution_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (1, "001_initial_core_schema", checksum, now, "SUCCESS"),
            )

    def _discover_migration_files(self) -> List[Tuple[int, str, str, str]]:
        """
        Discovers version scripts in jarvis/database/migrations/versions.
        Returns sorted list of (version, migration_id, ddl, checksum).
        """
        versions_dir = os.path.join(os.path.dirname(__file__), "versions")
        if not os.path.exists(versions_dir):
            return []

        pattern = os.path.join(versions_dir, "[0-9][0-9][0-9]_*.py")
        files = glob.glob(pattern)

        discovered = []
        for filepath in sorted(files):
            mod_name = os.path.splitext(os.path.basename(filepath))[0]
            try:
                spec = importlib.util.spec_from_file_location(mod_name, filepath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    ver = getattr(mod, "MIGRATION_VERSION", None)
                    m_id = getattr(mod, "MIGRATION_ID", mod_name)
                    ddl = getattr(mod, "MIGRATION_DDL", "")
                    if ver and ddl:
                        checksum = compute_checksum(ddl)
                        discovered.append((ver, m_id, ddl, checksum))
            except Exception as e:
                raise MigrationError(f"Failed to load migration script '{filepath}': {str(e)}") from e

        discovered.sort(key=lambda x: x[0])
        return discovered

    def discover_and_apply_pending(self, conn: sqlite3.Connection) -> List[str]:
        """
        Discovers all migration scripts, validates checksums of applied migrations,
        and executes pending migrations sequentially in atomic transactions.
        """
        self.run_initial_schema(conn)
        applied = self.get_applied_migrations(conn)
        applied_dict: Dict[int, MigrationRecord] = {m.version: m for m in applied}

        # Baseline check on v1 checksum
        v1_checksum = compute_checksum(CORE_SCHEMA_DDL)
        if 1 in applied_dict and applied_dict[1].checksum != v1_checksum:
            raise MigrationChecksumError(f"Migration version 1 checksum mismatch! Applied: {applied_dict[1].checksum}, Code: {v1_checksum}")

        applied_names: List[str] = ["001_initial_core_schema"]

        # Discover version 2+ scripts
        discovered = self._discover_migration_files()
        for ver, m_id, ddl, chk in discovered:
            if ver in applied_dict:
                # Validate checksum of previously applied migration
                if applied_dict[ver].checksum != chk:
                    raise MigrationChecksumError(f"Migration version {ver} ({m_id}) checksum mismatch! Applied: {applied_dict[ver].checksum}, Code: {chk}")
                applied_names.append(m_id)
            else:
                # Apply pending migration atomically
                now = time.time()
                with conn:
                    # Filter DDL if column already exists (safeguard for SQLite ALTER TABLE)
                    statements = [s.strip() for s in ddl.split(";") if s.strip()]
                    for stmt in statements:
                        try:
                            conn.execute(stmt)
                        except sqlite3.OperationalError as op_err:
                            if "duplicate column name" in str(op_err).lower():
                                continue
                            raise

                    conn.execute(
                        """
                        INSERT INTO schema_migrations (version, migration_id, checksum, applied_at, execution_status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (ver, m_id, chk, now, "SUCCESS"),
                    )
                applied_names.append(m_id)

        return applied_names
