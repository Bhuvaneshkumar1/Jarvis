"""
Thread-Safe SQLite Connection Factory, Connection Scope, & Async Wrapper for JARVIS (Batch 16).
"""

import asyncio
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator, Callable, Any, TypeVar, Optional
from jarvis.database.settings import DatabaseSettings, get_database_settings
from jarvis.database.exceptions import DatabaseConnectionError

T = TypeVar("T")

_CONNECTION_LOCK = threading.Lock()


def create_connection(settings: Optional[DatabaseSettings] = None) -> sqlite3.Connection:
    """
    Creates and configures a thread-safe, durable SQLite connection.
    Enforces WAL mode, foreign keys, busy timeout, and synchronous settings.
    """
    settings = settings or get_database_settings()
    db_path = settings.resolve_db_path()

    if db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to create database directory '{db_dir}': {str(e)}") from e

    try:
        conn = sqlite3.connect(
            db_path,
            timeout=settings.connection_timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # Apply PRAGMA settings
        if settings.foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON;")

        if db_path != ":memory:" and settings.journal_mode:
            conn.execute(f"PRAGMA journal_mode = {settings.journal_mode};")

        if settings.synchronous:
            conn.execute(f"PRAGMA synchronous = {settings.synchronous};")

        if settings.busy_timeout_ms:
            conn.execute(f"PRAGMA busy_timeout = {settings.busy_timeout_ms};")

        return conn
    except Exception as e:
        raise DatabaseConnectionError(f"Failed to open SQLite database connection at '{db_path}': {str(e)}") from e


@contextmanager
def connection_scope(settings: Optional[DatabaseSettings] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager yielding a thread-safe SQLite connection and guaranteeing cleanup upon exit.
    """
    conn = create_connection(settings)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def execute_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Execute blocking SQLite operation safely off the main asyncio event loop thread pool.
    Prevents blocking the application's async loop during database I/O.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
