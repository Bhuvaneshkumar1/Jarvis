"""
Authoritative Relational Schema Definitions for JARVIS Core Entities (Batch 16).
Preserves existing tasks, approvals, security, and policy tables while introducing foundational entities.
"""

CORE_SCHEMA_DDL = """
-- 1. Schema Migration History Table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    migration_id TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at REAL NOT NULL,
    execution_status TEXT NOT NULL
);

-- 2. Application Metadata Table
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- 3. Durable Principals Identity Table
CREATE TABLE IF NOT EXISTS principals (
    principal_id TEXT PRIMARY KEY,
    principal_type TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- 4. Security Sessions Table
CREATE TABLE IF NOT EXISTS security_sessions (
    session_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked_at REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    version INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (principal_id) REFERENCES principals(principal_id) ON DELETE CASCADE
);

-- 5. Policy References Table
CREATE TABLE IF NOT EXISTS policy_references (
    policy_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

-- 6. Task Management Tables (Preserved from Batch 6)
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    cancelled_at REAL,
    failed_at REAL,
    owner TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    parent_task_id TEXT,
    metadata TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    error_code TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL,
    dependency_task_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL DEFAULT 'REQUIRED',
    created_at REAL NOT NULL,
    PRIMARY KEY (task_id, dependency_task_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_history (
    history_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    timestamp REAL NOT NULL,
    reason TEXT,
    metadata TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

-- 7. Approval Policy Tables (Preserved from Batch 15)
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    principal_type TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    target_resource TEXT NOT NULL,
    exact_scope TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    task_id TEXT,
    correlation_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL,
    approver_id TEXT,
    decision_timestamp REAL,
    consumed_at REAL,
    consumed_by_task_id TEXT,
    operation_fingerprint TEXT,
    metadata TEXT NOT NULL
);

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
    metadata TEXT NOT NULL
);

-- 8. Core Performance & Integrity Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_principal ON security_sessions(principal_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON security_sessions(status);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_correlation ON tasks(correlation_id);
CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_principal ON approvals(principal_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_scoped_principal ON scoped_approvals(principal_id);
"""
