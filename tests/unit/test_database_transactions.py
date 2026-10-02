"""
Unit & Concurrency Tests for TransactionManager & Savepoint Handling (Batch 16).
"""

import os
import pytest
import tempfile
import threading
import time

from jarvis.database import (
    DatabaseSettings,
    TransactionManager,
    connection_scope,
    TransactionError,
    ConstraintViolationError,
)


@pytest.fixture
def temp_db_settings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "tx_test.db")
        settings = DatabaseSettings(db_path=db_path)
        with connection_scope(settings) as conn:
            conn.execute("CREATE TABLE test_data (id TEXT PRIMARY KEY, value TEXT NOT NULL);")
            conn.commit()
        yield settings


def test_transaction_commit_and_rollback(temp_db_settings):
    tx_mgr = TransactionManager(settings=temp_db_settings)

    # Successful commit
    with tx_mgr.transaction() as conn:
        conn.execute("INSERT INTO test_data (id, value) VALUES ('1', 'Alpha');")

    with connection_scope(temp_db_settings) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM test_data WHERE id = '1';")
        assert cursor.fetchone()["value"] == "Alpha"

    # Aborted rollback
    with pytest.raises(TransactionError):
        with tx_mgr.transaction() as conn:
            conn.execute("INSERT INTO test_data (id, value) VALUES ('2', 'Beta');")
            raise ValueError("Simulated operational failure")

    with connection_scope(temp_db_settings) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM test_data WHERE id = '2';")
        assert cursor.fetchone() is None


def test_nested_savepoint_transactions(temp_db_settings):
    tx_mgr = TransactionManager(settings=temp_db_settings)

    with tx_mgr.transaction() as conn:
        conn.execute("INSERT INTO test_data (id, value) VALUES ('10', 'Parent');")

        # Nested savepoint succeeds
        with tx_mgr.transaction(conn=conn) as conn2:
            conn2.execute("INSERT INTO test_data (id, value) VALUES ('11', 'Child');")

    with connection_scope(temp_db_settings) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_data WHERE id IN ('10', '11');")
        assert cursor.fetchone()[0] == 2


def test_foreign_key_and_constraint_enforcement(temp_db_settings):
    tx_mgr = TransactionManager(settings=temp_db_settings)

    with tx_mgr.transaction() as conn:
        conn.execute("INSERT INTO test_data (id, value) VALUES ('dup', 'First');")

    # Duplicate primary key MUST raise ConstraintViolationError
    with pytest.raises(ConstraintViolationError):
        with tx_mgr.transaction() as conn:
            conn.execute("INSERT INTO test_data (id, value) VALUES ('dup', 'Second');")


def test_concurrent_read_write_with_wal_mode(temp_db_settings):
    tx_mgr = TransactionManager(settings=temp_db_settings)
    errors = []

    def writer_thread():
        try:
            for i in range(20):
                with tx_mgr.transaction() as conn:
                    conn.execute("INSERT INTO test_data (id, value) VALUES (?, ?);", (f"w_{i}", f"val_{i}"))
                time.sleep(0.005)
        except Exception as e:
            errors.append(e)

    def reader_thread():
        try:
            for _ in range(20):
                with connection_scope(temp_db_settings) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM test_data;")
                    cursor.fetchone()
                time.sleep(0.005)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=writer_thread)
    t2 = threading.Thread(target=reader_thread)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert not errors
