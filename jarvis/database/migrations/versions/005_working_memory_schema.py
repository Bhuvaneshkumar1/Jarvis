"""
Migration 005: Persistent Working Memory Subsystem (Batch 25).
Creates working_memories table with scope indexing, ownership isolation, expiration, and JSON metadata.
"""

MIGRATION_VERSION = 5
MIGRATION_ID = "005_working_memory_schema"

MIGRATION_DDL = """
-- Persistent Working Memory Table
CREATE TABLE IF NOT EXISTS working_memories (
    memory_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    conversation_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    classification TEXT NOT NULL DEFAULT 'INTERNAL',
    priority INTEGER NOT NULL DEFAULT 5,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL,
    version INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'working_memory',
    metadata TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ACTIVE'
);

-- Query Optimization & Isolation Indexes
CREATE INDEX IF NOT EXISTS idx_working_memories_scope_owner ON working_memories(scope, owner_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_conversation ON working_memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_task ON working_memories(task_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_agent ON working_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_expires_status ON working_memories(expires_at, status);
CREATE INDEX IF NOT EXISTS idx_working_memories_priority ON working_memories(priority DESC, created_at DESC);
"""
