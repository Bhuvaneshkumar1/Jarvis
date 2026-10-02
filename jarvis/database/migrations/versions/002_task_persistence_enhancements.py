"""
Migration 002: Task Persistence Enhancements (Batch 17).
Adds task_type, idempotency_key, deadline_at, due_at, assigned_agent_id, cancellation_requested, error_summary.
"""

MIGRATION_VERSION = 2
MIGRATION_ID = "002_task_persistence_enhancements"

MIGRATION_DDL = """
-- Add missing columns to tasks table if not already present
ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'GENERAL';
ALTER TABLE tasks ADD COLUMN idempotency_key TEXT;
ALTER TABLE tasks ADD COLUMN deadline_at REAL;
ALTER TABLE tasks ADD COLUMN due_at REAL;
ALTER TABLE tasks ADD COLUMN assigned_agent_id TEXT;
ALTER TABLE tasks ADD COLUMN cancellation_requested INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN error_summary TEXT;

-- Create indexes for task lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_agent ON tasks(assigned_agent_id);
"""
