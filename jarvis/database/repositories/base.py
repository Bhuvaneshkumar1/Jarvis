"""
Abstract Base Repository Interface for JARVIS Relational Repositories (Batch 16).
"""

from typing import Optional, ContextManager
import sqlite3
from jarvis.database.manager import DatabaseManager
from jarvis.database.connection import connection_scope


class BaseRepository:
    """
    Abstract Base Class for all JARVIS database repositories.
    Obtains connections and transaction context through DatabaseManager.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager

    def get_connection(self) -> ContextManager[sqlite3.Connection]:
        """Obtain a scoped connection context."""
        if self.db_manager:
            return self.db_manager.connection()
        return connection_scope()

    def get_transaction(self, conn: Optional[sqlite3.Connection] = None) -> ContextManager[sqlite3.Connection]:
        """Obtain an atomic transaction context."""
        if self.db_manager:
            return self.db_manager.transaction(conn=conn)
        raise RuntimeError("DatabaseManager required for transaction scope.")
