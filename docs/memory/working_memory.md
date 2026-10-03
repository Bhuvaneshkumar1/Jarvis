# Working Memory System Architecture (Batch 25)

## Overview

The **Working Memory System** is the short-term context persistence layer for **JARVIS**. It allows conversation contexts, active task states, dynamic agent execution parameters, and session metadata to persist safely across runtime restarts and provider calls without resending full, unbounded conversation histories to LLM providers.

Working memory is distinct from future episodic, semantic, or project memory layers:
* **Working Memory (Batch 25)**: Short-term, scope-isolated, token-budgeted, timestamp-expired operational context.
* **Episodic Memory (Planned)**: Long-term history of past autonomous agent events and completed user interactions.
* **Semantic Memory (Planned)**: Knowledge graph and vector embeddings of domain facts and system skills.
* **Project Memory (Planned)**: Workspace code maps, repository architecture indexes, and project notes.

---

## Memory Scopes & Isolation

Working memory enforces strict owner isolation across six standardized scopes:

| Scope | Purpose | Ownership / Identification Rules |
| :--- | :--- | :--- |
| `CONVERSATION` | Current active chat context | Requires `owner_id` & `conversation_id` |
| `TASK` | Context relevant to an active background task | Requires `owner_id` & `task_id` |
| `AGENT` | Temporary execution context belonging to an agent | Requires `owner_id` & `agent_id` |
| `SESSION` | Interactive session state | Requires `owner_id` |
| `SYSTEM` | Authorized system-level working context | Requires explicit `SecurityLevel` authorization |
| `WORKING` | General short-term working context | Requires `owner_id` |

### Security & Privacy Rules
1. **Owner Isolation**: Requester `owner_id` must match memory `owner_id`. Cross-owner queries return empty results without disclosing memory existence.
2. **Classification Check**: Caller cannot view memories exceeding their authorized `max_classification` security level (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`).
3. **Secret Redaction**: Content passed to working memory is automatically scanned and redacted via `SecretRedactor` to prevent credential leakage.
4. **Expiration Enforcement**: Expired entries (`expires_at <= now`) are automatically filtered out during retrieval and marked `EXPIRED`.

---

## Database Persistence Schema

Working memory persistence uses SQLite WAL-mode transactional storage via migration `005_working_memory_schema`:

```sql
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

CREATE INDEX IF NOT EXISTS idx_working_memories_scope_owner ON working_memories(scope, owner_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_conversation ON working_memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_task ON working_memories(task_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_agent ON working_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_working_memories_expires_status ON working_memories(expires_at, status);
CREATE INDEX IF NOT EXISTS idx_working_memories_priority ON working_memories(priority DESC, created_at DESC);
```

---

## Selective Retrieval & Prioritization

The `SelectiveMemoryRetrievalEngine` ranks eligible memories using hard security filtering followed by deterministic soft scoring:

$$\text{Score} = (\text{Priority} \times 10.0) + \text{ScopeBonus} + \text{IDMatches} + \text{RecencyBonus} + \text{KeywordBonus}$$

* **Hard Filters**: Excluded if `status != ACTIVE`, `expires_at <= now`, `owner_id` mismatch, or `classification > max_classification`.
* **Tie-Breaker**: `(Score DESC, Priority DESC, CreatedAt DESC, MemoryID ASC)`.

### Context Token Budgeting
`TokenBudgetManager` estimates token usage (3.5 chars/token + metadata framing) and fits prioritized entries into `filter.token_budget` without silently truncating individual memory contents.

---

## Code Usage Example

```python
from jarvis.memory.working import WorkingMemoryManager, WorkingMemoryEntry, MemoryRetrievalFilter
from jarvis.core.enums import MemoryScope, SecurityLevel

# Initialize Manager
manager = WorkingMemoryManager()

# Create Working Memory Entry
entry = WorkingMemoryEntry(
    scope=MemoryScope.CONVERSATION,
    owner_id="user_123",
    conversation_id="conv_999",
    content="User prefers dark mode UI and concise response summaries.",
    priority=8,
)
manager.create(entry)

# Retrieve Selective Context within Token Budget
filter = MemoryRetrievalFilter(
    scopes=[MemoryScope.CONVERSATION],
    owner_id="user_123",
    conversation_id="conv_999",
    token_budget=500,
    limit=5,
)
memories = manager.retrieve(filter)
for mem in memories:
    print(f"[{mem.priority}] {mem.content}")
```
