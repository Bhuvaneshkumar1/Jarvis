"""
Migration 003: Approval Persistence Enhancements (Batch 18).
Creates/extends approvals, approval_decisions, approval_history, and scoped_approvals tables with versioning and indexes.
"""

MIGRATION_VERSION = 3
MIGRATION_ID = "003_approval_persistence_enhancements"

MIGRATION_DDL = """
-- Approvals Table Creation (if not exists)
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT,
    principal_id TEXT NOT NULL,
    principal_type TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    target_resource TEXT NOT NULL,
    exact_scope TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL,
    approver_id TEXT,
    decision_timestamp REAL,
    consumed_at REAL,
    consumed_by_task_id TEXT,
    operation_fingerprint TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    requester_id TEXT,
    decided_at REAL,
    cancelled_at REAL,
    decision_reason TEXT,
    policy_version TEXT,
    request_fingerprint TEXT
);

-- Alter Table Safeguards for Existing Database Schemas
ALTER TABLE approvals ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE approvals ADD COLUMN requester_id TEXT;
ALTER TABLE approvals ADD COLUMN decided_at REAL;
ALTER TABLE approvals ADD COLUMN cancelled_at REAL;
ALTER TABLE approvals ADD COLUMN decision_reason TEXT;
ALTER TABLE approvals ADD COLUMN policy_version TEXT;
ALTER TABLE approvals ADD COLUMN request_fingerprint TEXT;

-- Approval Decisions Audit Log Table
CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    approver_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    decision_reason TEXT,
    decided_at REAL NOT NULL,
    version_at_decision INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(approval_id) REFERENCES approvals(approval_id) ON DELETE CASCADE
);

-- Approval History Audit Log Table
CREATE TABLE IF NOT EXISTS approval_history (
    history_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    transition_reason TEXT NOT NULL,
    actor_id TEXT,
    timestamp REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(approval_id) REFERENCES approvals(approval_id) ON DELETE CASCADE
);

-- Scoped Approvals Table
CREATE TABLE IF NOT EXISTS scoped_approvals (
    approval_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    principal_type_class TEXT,
    task_id TEXT,
    allowed_actions TEXT NOT NULL,
    allowed_resources TEXT NOT NULL,
    max_risk_level TEXT NOT NULL,
    expires_at REAL NOT NULL,
    delegation_permitted INTEGER NOT NULL DEFAULT 0,
    max_uses INTEGER,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Indexes for Query Performance & Lookups
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_principal ON approvals(principal_id, status);
CREATE INDEX IF NOT EXISTS idx_approvals_fingerprint ON approvals(operation_fingerprint);
CREATE INDEX IF NOT EXISTS idx_approval_history_approval_id ON approval_history(approval_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_approval_id ON approval_decisions(approval_id, decided_at);

"""
