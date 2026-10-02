# JARVIS PIN Authentication Architecture (Batch 12)

## 1. Overview
The JARVIS Authentication Subsystem provides production-oriented, PIN-based primary user authentication. It enforces strict separation of concerns, constant-time cryptographic verification, secure credential storage, unpredictable session management, comprehensive audit trails, and security event publishing.

---

## 2. Authentication Architecture
```text
User Input
    │
    ▼
Authentication Manager (Authoritative Entry Point)
    ├──► PIN Policy Validator (PinPolicy)
    ├──► Cryptographic Hasher (PINHasher: PBKDF2-HMAC-SHA256 / Argon2id)
    ├──► Credential Store (PinCredentialStore: Atomic JSON Persistence)
    ├──► Session Manager (SessionManager: In-Memory / Unpredictable Tokens)
    ├──► Attempt Tracker (AttemptTracker: Rate-Limiting Foundation)
    ├──► Audit Logger (AuditLogger: Redacted Log Trails)
    └──► Event Bus (EventBus: Safe Security Events)
```

---

## 3. PIN Policy Rules
- **Minimum Length**: 6 digits (configurable).
- **Maximum Length**: 12 digits (configurable).
- **Input Restrictions**: Numeric ASCII digits (0-9) only. Non-ASCII digits, letters, symbols, whitespace, and empty inputs are strictly rejected.
- **Leading Zeroes**: Preserved deterministically by treating PIN inputs strictly as string instances (no integer casting).
- **Confirmation**: Enrollment and PIN change workflows require explicit confirmation string matching.

---

## 4. Cryptographic Specifications
- **Algorithm**: PBKDF2-HMAC-SHA256 (default 210,000 iterations).
- **Salt Generation**: 32 bytes of cryptographically secure random data (`secrets.token_bytes(32)`).
- **Constant-Time Verification**: Uses `hmac.compare_digest` for verifier comparison to eliminate timing side-channel attacks.
- **Plaintext Protection**: Raw PINs are never stored, logged, or serialized.

---

## 5. Credential Storage
- **Location**: `data/credentials/pin_credential_<principal>.json`.
- **Atomic Persistence**: Writes to temporary file, flushes/fsyncs to disk, and replaces target file atomically via `os.replace`.
- **Post-Write Verification**: Re-reads and validates persisted salt and verifier before returning success.
- **Corrupted Record Protection**: Tampered or invalid JSON records trigger `CredentialCorruptedError` and report `CREDENTIAL_CORRUPTED` status.

---

## 6. Session Lifecycle & Security
- **Token Generation**: Cryptographically secure 256-bit random tokens (`sess_` prefix with `secrets.token_urlsafe(32)`).
- **Absolute Expiration**: Configurable default TTL (8 hours / 28,800s).
- **Inactivity Timeout**: Configurable inactivity window (15 minutes / 900s).
- **Explicit Revocation**: `revoke_session(session_id)` and `revoke_all_sessions()`.
- **Application Restart Security**: Sessions are stored in-memory by default so application restart invalidates all active sessions, preventing stale session restoration.

---

## 7. Audit & Event Bus Integration
- **Audited Events**:
  - `PIN_ENROLLMENT_SUCCESS`, `PIN_ENROLLMENT_FAILURE`
  - `AUTHENTICATION_SUCCESS`, `AUTHENTICATION_FAILURE`
  - `PIN_CHANGE_SUCCESS`, `PIN_CHANGE_FAILURE`
  - `SESSION_CREATED`, `SESSION_EXPIRED`, `SESSION_REVOKED`, `SESSION_VALIDATION_FAILURE`
- **Security Events**:
  - `AuthenticationSucceededEvent`, `AuthenticationFailedEvent`, `SessionCreatedEvent`, `SessionRevokedEvent`, `PinChangedEvent`
- **Redaction**: All audit entries and event payloads are sanitized to exclude raw credentials.

---

## 8. Windows Security Considerations
- **Canonical Paths**: Storage paths resolved via `os.path.realpath`.
- **File Permissions**: Protected directory structure verified via file system permissions.
- **Process Isolation**: In-memory session tokens isolated within process address space.

---

## 9. Failure Behavior
- **Fail Closed**: Any storage, cryptographic, policy, or validation failure prevents authentication and session issuance.
- **Safe Error Codes**: Internal errors are mapped to safe diagnostic error codes (`INVALID_PIN`, `NOT_ENROLLED`, `POLICY_VALIDATION_FAILED`, `CREDENTIAL_CORRUPTED`, `STORAGE_ERROR`).

---

## 10. Deferred Features (Future Batches)
- **Batch 13**: Three-attempt brute-force lockout policy and rate-limiting enforcement.
- **Batch 14**: Security-question recovery workflow.
- **Voice Authentication**: Explicitly excluded.
