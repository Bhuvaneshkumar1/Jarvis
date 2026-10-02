"""
Authoritative Central Database Manager for JARVIS (Batch 16).
Integrates database lifecycle, connection pool, versioned migrations, transactions, and health checks with Runtime Context.
"""

import os
import sqlite3
import threading
import time
from enum import Enum
from typing import Optional, Generator
from contextlib import contextmanager

from jarvis.core.enums import RuntimeState
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.contracts.health import HealthStatusContract
from jarvis.core.logging import JarvisLogger

from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.connection import connection_scope
from jarvis.database.transactions import TransactionManager
from jarvis.database.migrations.runner import MigrationRunner
from jarvis.database.health import DatabaseHealthCheck
from jarvis.database.backup import DatabaseBackupManager
from jarvis.database.exceptions import (
    DatabaseInitializationError,
    DatabaseUnavailableError,
)


class DatabaseState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class DatabaseManager(LifecycleComponent):
    """
    Authoritative Centralized Database Manager.
    Coordinates connection management, transaction management, migration execution, and integrity checks.
    """

    def __init__(
        self,
        settings: Optional[DatabaseSettings] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.settings = settings or get_database_settings()
        self.logger = logger or JarvisLogger(component="DatabaseManager")
        self._db_state: DatabaseState = DatabaseState.UNINITIALIZED
        self._context: Optional[RuntimeContext] = None
        self._lock = threading.Lock()

        self.transaction_manager = TransactionManager(settings=self.settings)
        self.migration_runner = MigrationRunner(settings=self.settings)
        self.health_checker = DatabaseHealthCheck(settings=self.settings)
        self.backup_manager = DatabaseBackupManager(settings=self.settings)

    @property
    def name(self) -> str:
        return "DatabaseManager"

    @property
    def state(self) -> RuntimeState:
        if self._db_state == DatabaseState.READY:
            return RuntimeState.RUNNING
        elif self._db_state == DatabaseState.INITIALIZING:
            return RuntimeState.INITIALIZING
        elif self._db_state in (DatabaseState.CLOSING, DatabaseState.CLOSED):
            return RuntimeState.STOPPED
        elif self._db_state == DatabaseState.FAILED:
            return RuntimeState.FAILED
        return RuntimeState.STOPPED

    @property
    def db_state(self) -> DatabaseState:
        return self._db_state

    async def initialize(self, context: RuntimeContext) -> None:
        """Initialize DatabaseManager component with RuntimeContext."""
        self._context = context
        self._db_state = DatabaseState.INITIALIZING
        self.logger.info("Initializing DatabaseManager...")
        db_path = self.settings.resolve_db_path()

        if db_path != ":memory:":
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        self.logger.info(f"DatabaseManager initialized for path '{db_path}'.")

    async def start(self) -> None:
        """
        Start DatabaseManager lifecycle:
        1. Test connection
        2. Run integrity check
        3. Apply pending migrations
        4. Transition to READY
        """
        with self._lock:
            if self._db_state == DatabaseState.READY:
                return

            self._db_state = DatabaseState.INITIALIZING
            try:
                # 1. Connection check
                with connection_scope(self.settings) as conn:
                    # 2. Integrity check on startup if configured
                    if self.settings.integrity_check_on_startup:
                        self.health_checker.run_integrity_check(conn)

                    # 3. Automatic migrations
                    if self.settings.auto_migrate:
                        self.migration_runner.discover_and_apply_pending(conn)

                self._db_state = DatabaseState.READY
                self.logger.info("DatabaseManager started successfully and is READY.")
            except Exception as e:
                self._db_state = DatabaseState.FAILED
                self.logger.error(f"DatabaseManager start failed: {str(e)}")
                raise DatabaseInitializationError(f"Database initialization failed: {str(e)}") from e

    async def stop(self) -> None:
        """Gracefully stop DatabaseManager."""
        with self._lock:
            if self._db_state in (DatabaseState.CLOSING, DatabaseState.CLOSED):
                return
            self._db_state = DatabaseState.CLOSING
            self.logger.info("Closing DatabaseManager resources...")
            time.sleep(0.01)
            self._db_state = DatabaseState.CLOSED
            self.logger.info("DatabaseManager closed.")

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a database connection."""
        if self._db_state not in (DatabaseState.READY, DatabaseState.INITIALIZING):
            raise DatabaseUnavailableError(f"Cannot open connection when database is in '{self._db_state.value}' state.")

        with connection_scope(self.settings) as conn:
            yield conn

    @contextmanager
    def transaction(self, conn: Optional[sqlite3.Connection] = None, immediate: bool = True) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding an atomic database transaction."""
        if self._db_state not in (DatabaseState.READY, DatabaseState.INITIALIZING):
            raise DatabaseUnavailableError(f"Cannot execute transaction when database is in '{self._db_state.value}' state.")

        with self.transaction_manager.transaction(conn=conn, immediate=immediate) as tx_conn:
            yield tx_conn

    def check_integrity(self) -> None:
        """Explicitly run database integrity checks."""
        with self.connection() as conn:
            self.health_checker.run_integrity_check(conn)

    def backup(self, custom_filename: Optional[str] = None) -> str:
        """Create online database backup."""
        if self._db_state != DatabaseState.READY:
            raise DatabaseUnavailableError("Cannot backup database when not READY.")
        return self.backup_manager.create_backup(custom_filename=custom_filename)

    async def health(self) -> HealthStatusContract:
        """Report component health status."""
        h = self.health_checker.check_health()
        h.metadata["db_state"] = self._db_state.value
        return h
