"""
Authoritative Database Foundation Subsystem for JARVIS (Batch 16).
Exports DatabaseManager, TransactionManager, DatabaseSettings, ConnectionFactory,
MigrationRunner, DatabaseHealthCheck, DatabaseBackupManager, BaseRepository, and exceptions.
"""

from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.connection import create_connection, connection_scope, execute_async
from jarvis.database.transactions import TransactionManager
from jarvis.database.schema import CORE_SCHEMA_DDL
from jarvis.database.migrations.runner import MigrationRunner, MigrationRecord, compute_checksum
from jarvis.database.health import DatabaseHealthCheck
from jarvis.database.backup import DatabaseBackupManager
from jarvis.database.manager import DatabaseManager, DatabaseState
from jarvis.database.repositories.base import BaseRepository
from jarvis.database.exceptions import (
    DatabaseError,
    DatabaseConnectionError,
    DatabaseInitializationError,
    MigrationError,
    MigrationChecksumError,
    MigrationVersionError,
    TransactionError,
    IntegrityError,
    DatabaseUnavailableError,
    BackupError,
    RestoreValidationError,
    ConstraintViolationError,
)

__all__ = [
    "DatabaseSettings",
    "get_database_settings",
    "create_connection",
    "connection_scope",
    "execute_async",
    "TransactionManager",
    "CORE_SCHEMA_DDL",
    "MigrationRunner",
    "MigrationRecord",
    "compute_checksum",
    "DatabaseHealthCheck",
    "DatabaseBackupManager",
    "DatabaseManager",
    "DatabaseState",
    "BaseRepository",
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseInitializationError",
    "MigrationError",
    "MigrationChecksumError",
    "MigrationVersionError",
    "TransactionError",
    "IntegrityError",
    "DatabaseUnavailableError",
    "BackupError",
    "RestoreValidationError",
    "ConstraintViolationError",
]
