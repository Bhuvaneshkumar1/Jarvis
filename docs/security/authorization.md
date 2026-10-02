# Centralized Authorization, Policy & Approval Engine

## 1. Overview & Architecture

The JARVIS Authorization, Policy & Approval Engine is the single authoritative security component responsible for governing all system actions, tools, agents, tasks, file operations, system settings, and cybersecurity activities.

```
[ Authorization Request ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ 1. Identity & Session Verification                     │
├────────────────────────────────────────────────────────┤
│ 2. Permission Taxonomy & Delegation Check              │
├────────────────────────────────────────────────────────┤
│ 3. Path & Resource Normalization (Windows Safety)      │
├────────────────────────────────────────────────────────┤
│ 4. Risk Classification & Escalation Engine             │
├────────────────────────────────────────────────────────┤
│ 5. Scoped Approval Matching                            │
├────────────────────────────────────────────────────────┤
│ 6. Baseline Policy Rules A–G Evaluation                │
├────────────────────────────────────────────────────────┤
│ 7. Persistent Approval Requirement & Single-Use Check  │
└────────────────────────────────────────────────────────┘
          │
          ├── ALLOW
          ├── DENY (Fail Closed)
          └── REQUIRE_APPROVAL
```

---

## 2. Principal & Permission Model

Supported Principal Types:
- `USER`: Primary authenticated user session.
- `AGENT`: Autonomous or delegated agent instance.
- `SYSTEM`: Registered internal system service.
- `SCHEDULED_TASK`: System timer or scheduled task trigger.
- `INTEGRATION`: Third-party integration or web connector.

Permission Taxonomy:
- Filesystem: `filesystem.read`, `filesystem.create`, `filesystem.modify`, `filesystem.delete`, `filesystem.rename`, `filesystem.move`, `filesystem.execute`
- System Control: `system.app.launch`, `system.app.close`, `system.process.inspect`, `system.process.terminate`, `system.settings.read`, `system.settings.modify`, `system.shutdown`, `system.restart`
- Development: `code.read`, `code.create`, `code.modify`, `code.delete`, `code.test`, `code.build`, `git.status`, `git.commit`, `git.push`
- Agent Management: `agent.create`, `agent.spawn`, `agent.delegate`, `agent.terminate`, `agent.inspect`
- Integration: `integration.read`, `integration.write`, `integration.send`, `integration.delete`
- Cybersecurity: `security.recon`, `security.scan`, `security.analyze`, `security.exploit`, `security.credential_test`, `security.modify_target`

---

## 3. Risk Classification Rules

Risk Levels: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`

Deterministically computed by `classify_risk()`. Escalations apply for:
- Bulk operations / multiple targets -> Escalate to `CRITICAL`
- Sensitive system locations -> Escalate to `CRITICAL`
- Production / external targets -> Escalate to `HIGH`
- Irreversible destructive state -> Escalate to `HIGH`
- Attempted Risk Downgrade -> Strictly ignored and overridden by trusted calculation.

---

## 4. Default Security Policies (A–G)

- Policy A (File Reading): Permitted by default for authorized local operations. Credential & secret files require approval.
- Policy B (File Creation): Allowed within task workspace. Writes outside workspace or into sensitive system dirs denied.
- Policy C (File Modification): Requires explicit user approval or active scoped approval.
- Policy D (File Deletion): Requires explicit approval. Ambiguous targets rejected.
- Policy E (Git): Status allowed; commit & push require explicit separate user approvals.
- Policy F (High-Risk Ops): Require explicit user approval. Agents cannot self-approve high-risk user operations.
- Policy G (Cybersecurity Ops): Denies unknown targets. Distinguishes passive analysis from active testing. Active ops require explicit scope authorization context and approval.

---

## 5. Approval Engine & Lifecycle

Statuses: `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`, `CONSUMED`

Key Guarantee: Single-use atomic consumption immediately before execution with Time-Of-Check/Time-Of-Use (TOCTOU) revalidation against current policy.

Database Persistence Schema (`data/jarvis_policy.db`):
- `approvals` table
- `scoped_approvals` table
- `approval_audit_history` table

---

## 6. Verification Commands

To execute tests and verify the policy engine:
```bash
.venv\Scripts\python.exe -m pytest tests/unit/test_policy_engine.py tests/unit/test_approval_engine.py -v
.venv\Scripts\python.exe scripts/quality_gate.py
```
