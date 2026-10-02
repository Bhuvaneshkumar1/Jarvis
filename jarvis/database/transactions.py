"""
Reusable Transaction Management Layer & Savepoint Support for JARVIS (Batch 16).
"""

import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Generator, Optional
from jarvis.database.connection import create_connection
from jarvis.database.settings import DatabaseSettings
from jarvis.database.exceptions import TransactionError, ConstraintViolationError


class TransactionManager:
    """
    Manages atomic transactions, nested savepoints, retries on busy locks,
    and automatic rollback on exception.
    """

    def __init__(self, settings: Optional[DatabaseSettings] = None, max_retries: int = 3, backoff_base: float = 0.05):
        self.settings = settings
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    @contextmanager
    def transaction(
        self,
        conn: Optional[sqlite3.Connection] = None,
        immediate: bool = True,
    ) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for an atomic database transaction.
        If conn is provided, uses existing connection (with savepoints if transaction already active).
        Otherwise creates a new connection scope.
        """
        own_conn = False
        if conn is None:
            conn = create_connection(self.settings)
            own_conn = True

        in_transaction = conn.in_transaction
        savepoint_name = f"sp_{uuid.uuid4().hex[:8]}" if in_transaction else None

        attempts = 0
        while True:
            attempts += 1
            try:
                if in_transaction:
                    conn.execute(f"SAVEPOINT {savepoint_name};")
                else:
                    mode = "IMMEDIATE" if immediate else "DEFERRED"
                    conn.execute(f"BEGIN {mode};")

                yield conn

                if in_transaction:
                    conn.execute(f"RELEASE SAVEPOINT {savepoint_name};")
                else:
                    conn.commit()
                break

            except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                err_msg = str(e).lower()
                is_busy = "busy" in err_msg or "locked" in err_msg

                # Attempt rollback / release savepoint
                try:
                    if in_transaction and savepoint_name:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name};")
                        conn.execute(f"RELEASE SAVEPOINT {savepoint_name};")
                    else:
                        conn.rollback()
                except Exception:
                    pass

                if is_busy and attempts < self.max_retries:
                    time.sleep(self.backoff_base * (2 ** (attempts - 1)))
                    continue

                if isinstance(e, sqlite3.IntegrityError):
                    raise ConstraintViolationError(f"Database constraint violation: {str(e)}") from e

                raise TransactionError(f"Transaction failed and rolled back: {str(e)}") from e

            except Exception as e:
                try:
                    if in_transaction and savepoint_name:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name};")
                        conn.execute(f"RELEASE SAVEPOINT {savepoint_name};")
                    else:
                        conn.rollback()
                except Exception:
                    pass
                raise TransactionError(f"Transaction aborted due to error: {str(e)}") from e

            finally:
                if own_conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
