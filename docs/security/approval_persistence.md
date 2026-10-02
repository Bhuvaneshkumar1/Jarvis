# Approval Persistence Architecture & Lifecycle Integration (Batch 18)

## Overview
JARVIS Batch 18 establishes a durable, restart-safe, transaction-safe persistent approval engine.
All approval requests, lifecycle state transitions, decisions, and history entries are durably stored in the centralized SQLite database (`data/jarvis.db`) via versioned migrations (`003_approval_persistence_enhancements`).

---

## 1. Approval Persistence Architecture

The persistent approval architecture integrates:
- **`ApprovalStateMachine`**: Authoritative status transition and action fingerprinting validation engine.
- **`PolicyRepository`**: Thread-safe SQLite repository supporting optimistic locking (`version`), pagination, and transactional history recording.
- **`ApprovalEngine`**: Primary service governing approval request creation, decision authorization, action fingerprint matching, single-use atomic consumption, and event publication.
- **`ApprovalRecoveryService`**: Startup recovery component that scans for overdue pending requests, transitions them to `EXPIRED`, and updates linked tasks.
- **`TaskManager`**: Integrated lifecycle manager that pauses tasks in `WAITING_APPROVAL` and updates them to `READY` or `BLOCKED` upon decision.

```
+-------------------+       +-----------------------+       +-------------------+
|  Policy Engine    | ----> |    Approval Engine    | ----> | PolicyRepository  |
+-------------------+       +-----------------------+       +-------------------+
                                   |         |                        |
                                   v         v                        v
                        +--------------+  +--------------+   +------------------+
                        | Event Bus    |  | Audit Logger |   | SQLite Database  |
                        +--------------+  +--------------+   | (data/jarvis.db) |
                                                              +------------------+
```

---

## 2. Database Schema & Migration (003)

Migration `003_approval_persistence_enhancements` creates and extends four tables in the local SQLite database:

1. **`approvals`**:
   - `approval_id` (TEXT PRIMARY KEY)
   - `task_id` (TEXT)
   - `principal_id` (TEXT NOT NULL)
   - `principal_type` (TEXT NOT NULL)
   - `requested_action` (TEXT NOT NULL)
   - `target_resource` (TEXT NOT NULL)
   - `exact_scope` (TEXT NOT NULL)
   - `risk_level` (TEXT NOT NULL)
   - `reason` (TEXT NOT NULL)
   - `correlation_id` (TEXT NOT NULL)
   - `created_at` (REAL NOT NULL)
   - `expires_at` (REAL NOT NULL)
   - `status` (TEXT NOT NULL)
   - `approver_id` (TEXT)
   - `decision_timestamp` (REAL)
   - `decided_at` (REAL)
   - `cancelled_at` (REAL)
   - `decision_reason` (TEXT)
   - `consumed_at` (REAL)
   - `consumed_by_task_id` (TEXT)
   - `operation_fingerprint` (TEXT)
   - `request_fingerprint` (TEXT)
   - `policy_version` (TEXT DEFAULT '1.0.0')
   - `version` (INTEGER NOT NULL DEFAULT 1)
   - `metadata` (TEXT NOT NULL DEFAULT '{}')

2. **`approval_decisions`**:
   - Audit log of formal decisions (`APPROVED`, `REJECTED`, `CANCELLED`).

3. **`approval_history`**:
   - Immutable audit trail of every status transition (`PENDING` -> `APPROVED` / `REJECTED` / `EXPIRED` / `CANCELLED` -> `CONSUMED`).

4. **`scoped_approvals`**:
   - Persistent representation of multi-use / duration-bound scoped authorizations.

### Indexes
- `idx_approvals_status` ON `approvals(status, expires_at)`
- `idx_approvals_task_id` ON `approvals(task_id)`
- `idx_approvals_principal` ON `approvals(principal_id, status)`
- `idx_approvals_fingerprint` ON `approvals(operation_fingerprint)`
- `idx_approval_history_approval_id` ON `approval_history(approval_id, timestamp)`
- `idx_approval_decisions_approval_id` ON `approval_decisions(approval_id, decided_at)`

---

## 3. Approval Lifecycle & Permitted Transitions

State machine rules enforced by `ApprovalStateMachine`:

| Current State | Target State | Permitted | Description / Rule |
| :--- | :--- | :--- | :--- |
| `PENDING` | `APPROVED` | YES | Allowed after approver principal authorization |
| `PENDING` | `REJECTED` | YES | Allowed after approver decision |
| `PENDING` | `EXPIRED` | YES | Allowed when `current_time >= expires_at` |
| `PENDING` | `CANCELLED` | YES | Allowed when cancelled by requester or authorized actor |
| `APPROVED` | `CONSUMED` | YES | Allowed on single-use execution consumption |
| `APPROVED` | `APPROVED` | NO | Duplicate decision rejected (`DuplicateDecisionError`) |
| `REJECTED` | * | NO | Terminal state; immutability enforced |
| `EXPIRED` | * | NO | Terminal state; immutability enforced |
| `CANCELLED` | * | NO | Terminal state; immutability enforced |
| `CONSUMED` | * | NO | Terminal state; single-use guarantee enforced |

---

## 4. Action Fingerprint & Scope Enforcement

To prevent Time-of-Check to Time-of-Use (TOCTOU) attacks and unauthorized parameter mutation:
- Every `ApprovalRequest` generates a deterministic SHA-256 `request_fingerprint` covering:
  - `requested_action`
  - `target_resource`
  - `exact_scope`
  - `risk_level`
  - Non-sensitive parameters (excluding secrets, credentials, and display timestamps)
- When a decision or consumption is attempted, `ApprovalStateMachine.validate_fingerprint` verifies that the requested action fingerprint matches the stored request fingerprint.
- If parameters are altered after approval creation, execution is denied with `FingerprintMismatchError`.

---

## 5. Expiry & Restart Recovery

- Expiration timestamps (`expires_at`) are stored in UTC seconds.
- `ApprovalRecoveryService` runs during system startup and scheduled maintenance cycles:
  1. Executes `PolicyRepository.expire_outdated_approvals(now)`.
  2. Overdue `PENDING` requests transition to `EXPIRED`.
  3. If an expired request is bound to a `task_id`, `TaskManager` transitions the task from `WAITING_APPROVAL` to `BLOCKED`.
  4. Startup recovery is strictly idempotent.

---

## 6. Security Controls

1. **Authentication & Session Security**: Approving user actions requires a valid, active authenticated session.
2. **Agent Self-Approval Prevention**: Agents cannot approve their own requests or high-risk (`HIGH`, `CRITICAL`) operations.
3. **Optimistic Concurrency**: Concurrent decision requests against the same approval are governed by `version` checks (`WHERE approval_id = ? AND version = ?`). Exactly one decision succeeds; concurrent collisions raise `StaleApprovalVersionError`.
4. **Audit Fail-Closed**: Every lifecycle transition writes to `AuditLogger` and publishes to `EventBus`. If durable audit writing fails, security decisions fail closed.

---

## 7. Verification & Tests

Executed test commands:
- Unit & State Machine Tests: `pytest tests/unit/test_approval_state_machine.py -v` (PASSED)
- Persistence & Integration Tests: `pytest tests/unit/test_approval_persistence.py -v` (PASSED)
- Concurrency & Security Tests: `pytest tests/unit/test_approval_concurrency_security.py -v` (PASSED)
- Recovery & Task Sync Tests: `pytest tests/unit/test_approval_recovery.py -v` (PASSED)
- Complete Project Test Suite: `pytest -v` (252 tests PASSED)
- Quality Gate: `python scripts/quality_gate.py` (8 / 8 Checks PASSED)
