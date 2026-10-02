"""
Migration 004: Persistent State Recovery and Event Outbox Infrastructure (Batch 19).
Creates recovery_executions, recovery_locks, and event_outbox tables with versioning and indexes.
"""

MIGRATION_VERSION = 4
MIGRATION_ID = "004_state_recovery_outbox"

MIGRATION_DDL = """
-- Persistent Recovery Executions History Table
CREATE TABLE IF NOT EXISTS recovery_executions (
    recovery_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    inspected_count INTEGER NOT NULL DEFAULT 0,
    recovered_count INTEGER NOT NULL DEFAULT 0,
    reconciled_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    manual_intervention_count INTEGER NOT NULL DEFAULT 0,
    details TEXT NOT NULL DEFAULT '{}'
);

-- Recovery Lock Table for Concurrency & Fencing
CREATE TABLE IF NOT EXISTS recovery_locks (
    lock_name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    fencing_token INTEGER NOT NULL DEFAULT 1
);

-- Event Outbox Table for Process Interruptions and Reliable Publishing
CREATE TABLE IF NOT EXISTS event_outbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    correlation_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at REAL NOT NULL,
    dispatched_at REAL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_error TEXT
);

-- Query Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_recovery_executions_status ON recovery_executions(status, started_at);
CREATE INDEX IF NOT EXISTS idx_event_outbox_status ON event_outbox(status, created_at);
"""
