"""
Typed Exceptions for JARVIS Database Infrastructure (Batch 16).
"""

from jarvis.core.exceptions import JarvisError


class DatabaseError(JarvisError):
    """Base exception for all database operations and manager failures."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when opening or configuring a database connection fails."""

    pass


class DatabaseInitializationError(DatabaseError):
    """Raised when database startup or schema initialization fails."""

    pass


class MigrationError(DatabaseError):
    """Base exception for schema migration failures."""

    pass


class MigrationChecksumError(MigrationError):
    """Raised when an already-applied migration file checksum mismatch is detected."""

    pass


class MigrationVersionError(MigrationError):
    """Raised when migration ordering or versioning is invalid."""

    pass


class TransactionError(DatabaseError):
    """Raised when a database transaction fails or rolls back unexpectedly."""

    pass


class IntegrityError(DatabaseError):
    """Raised when database integrity checks or foreign-key validations fail."""

    pass


class DatabaseUnavailableError(DatabaseError):
    """Raised when attempting database operations while the database manager is uninitialized or closed."""

    pass


class BackupError(DatabaseError):
    """Raised when creating or validating a database backup fails."""

    pass


class RestoreValidationError(DatabaseError):
    """Raised when a database backup file fails pre-restore integrity validation."""

    pass


class ConstraintViolationError(DatabaseError):
    """Raised when a database unique constraint or foreign key check fails."""

    pass
