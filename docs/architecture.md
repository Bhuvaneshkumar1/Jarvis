# JARVIS Architecture Documentation — Batch 5 Event Bus Baseline

## Target High-Level System Architecture

```text
User / Signal
 ↓
Main Entry Point (main.py)
 ↓
JarvisApplication Runtime Kernel [IMPLEMENTED - BATCH 4]
 ├── RuntimeState (STOPPED -> STARTING -> INITIALIZING -> RUNNING -> STOPPING -> STOPPED / FAILED)
 ├── ComponentRegistry (Dependency validation, topological ordering, cycle detection)
 ├── RuntimeContext (Shared app_id, session_id, settings, logger, cancellation_event)
 └── EventBus Infrastructure [IMPLEMENTED - BATCH 5]
      ├── Priority Queue & Worker Dispatch Loop (Async + Sync Handlers)
      ├── Subscriptions (Typed Events, Wildcard '*', Retry Policy, Timeout)
      ├── Diagnostic Ring Buffer (Bounded event history)
      └── Health & Audit Integration
 ↓
Core Contracts & Config Baseline [IMPLEMENTED - BATCH 2]
 ↓
Planner / Agent Manager / LLM Router [PLANNED - FUTURE BATCHES]
```

## Subsystem Implementation Status Matrix

| Subsystem Directory | Component Purpose | Current Status |
|---|---|---|
| `jarvis/core/events` | Authoritative Internal Event Bus & Messaging Infrastructure | IMPLEMENTED AND VERIFIED |
| `jarvis/core/runtime` | Authoritative Application Runtime Kernel & Lifecycle Manager | IMPLEMENTED AND VERIFIED |
| `jarvis/core` | Core exception hierarchy, daily audit logger, config foundation, contracts | IMPLEMENTED AND VERIFIED |
| `config/` | Environment & typed settings validation | IMPLEMENTED AND VERIFIED |
| `scripts/` | Quality gate local runner (`quality_gate.py`) | IMPLEMENTED AND VERIFIED |
| `.github/workflows/` | Automated CI pipeline (`ci.yml`) | IMPLEMENTED AND VERIFIED |
| `jarvis/agents/` | Dynamic subagent spawning & lifecycle management | PLANNED |
| `jarvis/llm/` | Multi-provider LLM routing & privacy filtering | PLANNED |
| `jarvis/memory/` | Context indexing & selective retrieval | PLANNED |
| `jarvis/tools/` | Tool registry & execution wrappers | PLANNED |
| `jarvis/security/` | Security policy engine & approval controls | PLANNED |
| `jarvis/verification/` | Empirical precondition & postcondition verification | PLANNED |


## Subsystem Single Authoritative Implementation Rule (Section 21)

Every subsystem defined maintains **EXACTLY ONE** authoritative implementation.
`jarvis.core.runtime.application.JarvisApplication` is the sole authoritative runtime application manager in the repository.
Duplicate variant implementations (e.g. `AdvancedOrchestrator`, `UniversalOrchestrator`) are strictly prohibited to prevent architectural drift.

