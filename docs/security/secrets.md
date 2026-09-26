# JARVIS AI OS — Secrets Management & Credential Security Architecture (Batch 10)

## 1. Overview
The **Secrets Management and Credential Security Subsystem** provides authoritative, encrypted, least-privilege credential protection across the entire JARVIS application lifecycle.

It separates non-secret operational configuration (Batch 8/9) from sensitive secrets and credentials, preventing hardcoded keys, accidental log disclosure, unauthorized inter-component access, or unsafe credential persistence.

---

## 2. Architecture & Components

```text
       +--------------------------------------------------+
       |             SecretsManager (Facade)              |
       +------------------------+-------------------------+
                                |
         +----------------------+----------------------+
         |                                             |
+--------v-------------------+             +-----------v------------+
|   SecretPolicyEvaluator    |             |     SecretRedactor     |
| (Least Privilege & Audit)  |             | (Anti-Leak Sanitizer)  |
+----------------------------+             +------------------------+
                 |
                 +-------------------+
                                     |
                         +-----------v------------+
                         | CompositeSecretProvider|
                         +-----------+------------+
                                     |
               +---------------------+---------------------+
               |                                           |
+--------------v---------------+             +-------------v--------------+
| EncryptedFileSecretProvider  |             | EnvironmentSecretProvider  |
|  (Fernet AES-128-CBC+HMAC)   |             |  (Registry & Pattern Env)  |
+------------------------------+             +----------------------------+
```

### Core Components
* **`SecretsManager`**: Facade managing secret loading, storage, policy evaluation, rotation, and diagnostic reporting.
* **`MasterKeyManager`**: Owns 32-byte URL-safe base64 master key loading, validation, generation, and file protection.
* **`EncryptedSecretStore`**: Authenticated local secret store utilizing `Fernet` (AES-128-CBC + HMAC-SHA256), atomic crash-safe replacement, and format versioning.
* **`SecretPolicyEvaluator`**: Enforces component identity access scoping (`DEFAULT_COMPONENT_PERMISSIONS`) and emits structured non-leaking audit logs.
* **`SecretRedactor`**: Centralized anti-leak utility redacting raw secrets, headers (`Bearer`), credentials in URLs, dictionaries, and tracebacks.
* **`SecretValue`**: Immutable value container overriding `__repr__` and `__str__` to prevent accidental string logging.

---

## 3. Secret Classifications & Types

Secrets are categorized by severity:
1. **`PUBLIC`**: Non-sensitive application parameters (`JARVIS_ENV`, `JARVIS_LOG_LEVEL`).
2. **`INTERNAL`**: Internal operational settings (`JARVIS_EVENT_QUEUE_SIZE`, `JARVIS_LOG_DIR`).
3. **`SENSITIVE`**: Privacy-impacting options (`JARVIS_DATABASE_PATH`, `JARVIS_SECURITY_STRICT_MODE`).
4. **`SECRET`**: Standard API credentials & tokens (`NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `GITHUB_TOKEN`).
5. **`CRITICAL_SECRET`**: Core infrastructure security keys (`MASTER_ENCRYPTION_KEY`, `PRIVATE_KEY`).

---

## 4. Master Key & Encrypted Storage Design

* **Algorithm**: `Fernet` (AES-128-CBC with HMAC-SHA256 for authenticated encryption).
* **Master Key Loading**: Loaded from `JARVIS_MASTER_KEY` environment variable or `data/secrets/master.key`.
* **Atomic Replacement**: Store updates write to a temporary file in the same directory, flush to disk via `os.fsync()`, and perform atomic replacement (`os.replace`).
* **Tamper Detection**: Unauthenticated or tampered ciphertext triggers `InvalidToken` and raises `EnvironmentSecurityError`.

---

## 5. Least-Privilege Access Control Policy

A component must explicitly request secret access via `SecretAccessRequest`.
The `SecretPolicyEvaluator` verifies permissions:
* `llm_router` -> Authorized for `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
* `telegram` -> Authorized for `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`.
* `github` -> Authorized for `GITHUB_TOKEN`, `GITHUB_FINE_GRAINED_TOKEN`.
* `database` -> Authorized for `DATABASE_PASSWORD`, `JARVIS_DATABASE_PATH`.
* `system_admin` / `runtime` -> Full access including `CRITICAL_SECRET`.

---

## 6. Secret Redaction & Anti-Leakage
All raw secret values are registered with `SecretRedactor`.
Automatic sanitization applies to:
* Logs & Exception tracebacks
* Bearer & Basic Authorization headers
* Database connection URLs (`postgres://user:pass@host`)
* Structured dictionary & JSON payloads
* Diagnostic snapshots (`SET` / `NOT SET` metadata reporting only)

---

## 7. Rotation & Rollback Workflow
1. Requester issues `SecretRotationRequest`.
2. Format is validated via `CredentialValidator`.
3. New secret is encrypted and committed to store.
4. Read-back verification verifies payload integrity.
5. If verification fails, automatic rollback restores the previous valid secret.

---

## 8. Threat Model & Known Limitations

### Threat Model
* **Credential Exposure via Logs**: Prevented by `SecretValue` wrapper and `SecretRedactor`.
* **Cross-Component Credential Theft**: Prevented by `SecretPolicyEvaluator`.
* **Store File Tampering**: Prevented by Fernet HMAC-SHA256 authentication tag verification.
* **Crash Corruption**: Prevented by atomic temp file replacement and `fsync()`.

### Known Limitations
* **Python Memory Semantics**: Ordinary immutable Python strings do not support zeroization guarantees; plaintext lifetime is minimized.
* **Remote Rotation**: Remote provider API rotation hooks are marked deferred to future integration phases.

---

## 9. Operational Procedures & CLI Tools

### CLI Commands (`scripts/manage_secrets.py`)
```bash
# View safe diagnostics snapshot
python scripts/manage_secrets.py status

# List non-sensitive inventory
python scripts/manage_secrets.py list

# Validate credential presence and format
python scripts/manage_secrets.py validate

# Initialize master key file
python scripts/manage_secrets.py init-key
```
