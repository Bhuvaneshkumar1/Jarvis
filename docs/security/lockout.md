# JARVIS Three-Attempt PIN Lockout Architecture (Batch 13)

## 1. Overview
Batch 13 establishes a persistent, tamper-resistant, concurrency-safe PIN attempt tracking and lockout subsystem for JARVIS.

After **three consecutive failed PIN authentication attempts**, JARVIS locks PIN authentication for the principal, revokes all active authenticated sessions, and prevents further authentication attempts until authorized recovery (Batch 14) is completed.

---

## 2. Lockout Architecture & Flow

```text
User Submits PIN
       │
       ▼
Check Persistent Lockout State (LockoutManager & LockoutStore)
       │
       ├──► State: LOCKED ────────────────────────────────────► Deny Request (ACCOUNT_LOCKED)
       │                                                         (Do NOT invoke PIN verifier)
       │
       └──► State: UNLOCKED
               │
               ▼
       Verify Candidate PIN (PINHasher)
               │
       ┌───────┴───────┐
       │               │
    SUCCESS          FAILURE
       │               │
       ▼               ▼
 Reset Failure    Increment Failure Counter (Atomic CAS / Process Lock)
 Counter (0)           │
       │         ┌─────┴─────┐
       ▼         │           │
 Create Session  < 3        >= 3
 (AuthSession)   │           │
                 ▼           ▼
              Reject      Trigger Lockout (LOCKED)
             (INVALID_PIN)   ├──► Save Persistent Lockout Record
                             ├──► Revoke ALL Active Sessions
                             ├──► Audit PIN_LOCKOUT_TRIGGERED
                             └──► Publish PinLockoutTriggeredEvent
```

---

## 3. Lockout Policy & Matrix
| Failure Sequence | Result | Failure Count | Lockout State | Active Sessions |
| :--- | :--- | :---: | :---: | :---: |
| Attempt 1 (Failed) | `INVALID_PIN` | 1 | `ATTEMPT_TRACKING` | Retained |
| Attempt 2 (Failed) | `INVALID_PIN` | 2 | `ATTEMPT_TRACKING` | Retained |
| Attempt 3 (Failed) | `ACCOUNT_LOCKED` | 3 | `LOCKED` | **Revoked** |
| Attempt 4 (Failed/Correct) | `ACCOUNT_LOCKED` | 3 | `LOCKED` | Denied |
| Restart Process | `ACCOUNT_LOCKED` | 3 | `LOCKED` | Denied (Preserved) |

---

## 4. Consecutive Failure Semantics
- A failure increments the consecutive failure counter.
- A successful PIN authentication when unlocked resets the consecutive failure counter to `0`.
- A correct PIN submitted while locked is denied without resetting the failure counter.

---

## 5. Persistent & Atomic Storage
- **File Path**: `data/credentials/pin_lockout_<principal>.json`.
- **Atomic Operations**: Thread-safe (`threading.Lock`) and process-atomic via temporary file creation, `fsync()`, and `os.replace()`.
- **Post-Write Verification**: Re-reads and validates persisted state before returning.
- **Fail Closed**: Corrupted or tampered lockout files raise `CredentialCorruptedError` and return `CREDENTIAL_CORRUPTED` status.

---

## 6. Audit & Security Events
- **Audit Actions**: `PIN_ATTEMPT_FAILED`, `PIN_ATTEMPT_SUCCEEDED`, `PIN_LOCKOUT_TRIGGERED`, `PIN_AUTHENTICATION_BLOCKED`, `PIN_FAILURE_COUNTER_RESET`, `SESSION_REVOKED_DUE_TO_LOCKOUT`.
- **Security Events**: `PinAttemptFailedEvent`, `PinAttemptSucceededEvent`, `PinLockoutTriggeredEvent`, `PinAuthenticationBlockedEvent`, `SessionRevokedDueToLockoutEvent`.

---

## 7. Deferred Recovery Interface (Batch 14)
- `LockoutRecoveryService` provides the interface boundary for Batch 14 Security Question Recovery.
- In Batch 13, recovery methods return unsupported status / raise `NotImplementedError`. No unauthorized lockout resets are permitted.
