# JARVIS — System Architecture Documentation

## Core Design Principles

JARVIS strictly implements the personal autonomous AI assistant architecture for Windows without prohibited abstractions (No MCP, Kubernetes, cloud-only lock-ins).

### Central Orchestration Pipeline Sequence

All user and autonomous operations strictly execute through the following 11-stage pipeline:

```
REQUEST
  ↓
UNDERSTAND
  ↓
RETRIEVE
  ↓
PLAN
  ↓
AUTHORIZE (Policy Engine - Rule 10 & Fail Closed Rule 26)
  ↓
DELEGATE (Dynamic Temporary Agent Spawning & Isolation)
  ↓
EXECUTE (Tool Registry Wrappers & Execution)
  ↓
VERIFY (Verification Engine & Concrete Pre/Post-Conditions - Rule 11)
  ↓
RECOVER / ROLLBACK (LIFO State Restoration on Failure - Rule 12)
  ↓
REMEMBER (Selective Context Memory Indexing)
  ↓
REPORT (Daily Immutable Audit Log - Rule 18 & 19)
```

## Security & Privacy Guardrails

1. **Policy Engine (`jarvis.core.policy`)**:
   - `READ`: Allowed by default.
   - `CREATE`: Permitted under task creation policy or user approval.
   - `MODIFY`: Requires explicit approval unless current task scope holds explicit authorization.
   - `DELETE`: Explicit user authorization required.
   - `GIT_COMMIT` / `GIT_PUSH`: Explicit user authorization required.
   - `FINANCIAL`: Strict user authorization required.
   - `Fail Closed`: Actions with ambiguous risk levels or unverified permissions are denied by default.

2. **Verification Engine (`jarvis.core.verification`)**:
   - Never accepts model output or LLM responses as proof of execution success.
   - Enforces filesystem verification (existence, size, mtime updates), exit codes, and output checksums.

3. **Rollback Manager (`jarvis.core.rollback`)**:
   - Tracks modified and created files using atomic LIFO state backups.
   - On execution or verification failure, restores previous file state and cleans up temporary files.

4. **Immutable Audit Logging (`jarvis.core.audit_log`)**:
   - Logs events to daily files `logs/YYYYMMDD_log.txt`.
   - Automatically redacts API keys, bearer tokens, passwords, and sensitive credentials.

5. **Resource Limits (`jarvis.core.resource_monitor`)**:
   - Hard maximum memory budget of 8192 MB (8 GB RAM).
   - Normal operating target: 4-6 GB RAM.
