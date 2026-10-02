# JARVIS Architecture Documentation — Batch 19: Persistent State Recovery & Consistency

## 1. Overview
The **Persistent State Recovery Subsystem** guarantees deterministic, restart-safe recovery of application state following unexpected process termination, power loss, database disconnects, or crashed workflows.

It builds upon the Batch 16 SQLite database migration foundation, Batch 17 persistent task repository, and Batch 18 approval persistence engine without introducing competing managers or bypassing security authorization policies.

---

## 2. Architecture & Subsystem Structure

```text
JarvisApplication (Runtime Kernel)
     │
     ▼ (Phase 5 of Startup Sequence)
RecoveryCoordinator (core.recovery.coordinator)
     ├── Database Connection & Version Validation
     ├── Execution Lock Manager (recovery_locks table with fencing tokens)
     ├── Integrity Engine (PRAGMA integrity_check + relation validation)
     ├── Handlers:
     │     ├── TaskRecoveryHandler (Classifies side-effects & updates state)
     │     ├── ApprovalRecoveryHandler (Expires overdue requests & syncs tasks)
     │     └── EventOutboxHandler (Flushes un-dispatched post-commit events)
     └── RecoveryRepository (Persists run metrics to recovery_executions table)
```

### Core Components (`jarvis/core/recovery/`)
- `models.py`: Data models (`RecoveryStatus`, `OperationClassification`, `RecoveryRecord`, `OutboxEventRecord`).
- `store.py`: Persistence interface (`RecoveryRepository`) managing execution locks, database integrity checks, run records, and outbox queue operations.
- `handlers.py`:
  - `TaskRecoveryHandler`: Evaluates persisted tasks against execution guarantees and side-effects.
  - `ApprovalRecoveryHandler`: Scans pending approval requests, expires overdue entries, and synchronizes associated task state.
  - `EventOutboxHandler`: Manages durable post-commit event outbox queues.
- `coordinator.py`: Authoritative 16-step startup recovery sequence driver.

---

## 3. Startup Recovery Sequence

1. Initialize configuration.
2. Initialize secrets and security infrastructure.
3. Initialize database connection manager.
4. Validate database connectivity and schema version (Migration 004 verified).
5. Run safe database integrity checks (`validate_database_integrity`).
6. Acquire database recovery execution lock (`recovery_locks`).
7. Inspect persisted task and approval records.
8. Recover and expire overdue approvals.
9. Reconcile interrupted approval and task workflows.
10. Identify interrupted or uncertain operations.
11. Recover tasks according to their persisted states and execution guarantees.
12. Reconcile recoverable events and pending outbox records.
13. Validate resulting database and lifecycle invariants.
14. Persist structured recovery report (`recovery_executions`).
15. Release recovery lock.
16. Allow runtime to activate components that depend on successful recovery.

---

## 4. Recovery State Model

### Subsystem Recovery Execution States (`RecoveryStatus`)
- `NOT_STARTED`
- `INSPECTING`
- `RECOVERING`
- `RECONCILING`
- `VERIFYING`
- `COMPLETED`
- `COMPLETED_WITH_WARNINGS`
- `FAILED`
- `BLOCKED`

### Interrupted Operation Classification (`OperationClassification`)
- `CONFIRMED_NOT_EXECUTED`: Task safe to queue for execution.
- `CONFIRMED_EXECUTED`: Task completed prior to crash.
- `SAFE_TO_RETRY`: Idempotent operation with remaining retries; transitioned to `RETRY_PENDING`.
- `REQUIRES_RECONCILIATION`: State inconsistent; requiring workflow synchronization.
- `REQUIRES_MANUAL_INTERVENTION`: Uncertain non-idempotent side-effects detected; set to `BLOCKED`.
- `INVALID_OR_INCONSISTENT`: Corrupted or invalid state payload.

---

## 5. Task & Approval Recovery Rules

### Task Recovery Rules
1. **Terminal Task States**: `COMPLETED`, `CANCELLED`, `FAILED` are preserved intact. Never restarted.
2. **Executing Tasks (`RUNNING`)**: Interrupted tasks transition to `INTERRUPTED`. If retries remain and action is idempotent, transitioned to `RETRY_PENDING`. If retries exhausted or side-effect non-idempotent, transitioned to `BLOCKED`.
3. **Paused Tasks (`PAUSED`)**: Preserved as `PAUSED`.
4. **Waiting Tasks (`WAITING_APPROVAL`, `WAITING_DEPENDENCY`)**: Preserved unless dependency/approval expires.

### Approval Recovery Rules
1. **Terminal Decision States**: `APPROVED`, `REJECTED`, `CANCELLED` remain terminal.
2. **Expired Approvals**: Pending approvals past `expires_at` are expired to `EXPIRED`.
3. **Task Synchronization**: Tasks waiting on an expired approval are moved to `BLOCKED` or `CANCELLED` safely.

---

## 6. Recovery Locking & Concurrency Protection

- **Database-Level Lock**: Uses `recovery_locks` with a single lock key `startup_recovery_lock`.
- **Owner Identification**: Each coordinator generates a unique `owner_id`.
- **Fencing Token**: Incremental `fencing_token` prevents stale recovery owners from committing updates.
- **Abandoned Lock Takeover**: Locks older than 300 seconds (configurable) are automatically acquired by active nodes.

---

## 7. Durable Event Outbox

- **Table**: `event_outbox`
- **Schema**: `event_id`, `event_type`, `payload`, `status`, `retry_count`, `max_retries`, `created_at`, `delivered_at`, `error_message`.
- **Behavior**: Outbox records are written transactionally alongside state updates. The `EventOutboxHandler` flushes pending outbox records to the internal `EventBus` post-commit.

---

## 8. Security & Fail-Closed Guardrails

- **Authorization Policy**: Automatic recovery can only be initiated by the trusted runtime application kernel.
- **Credential Protection**: Secrets and Sensitive metadata are never logged or stored in unredacted recovery run diagnostics.
- **Fail-Closed Policy**: If database corruption is detected (`PRAGMA integrity_check` fails), recovery aborts with `RecoveryIntegrityError` and prevents application startup.
