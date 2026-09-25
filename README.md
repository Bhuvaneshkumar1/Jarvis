# JARVIS — Personal Autonomous AI Assistant (Windows-First)

```text
Project status:
APPLICATION KERNEL BASELINE / NOT PRODUCTION READY
```

## Purpose

JARVIS is a Windows-first personal autonomous AI assistant engineering project built following strict production guidelines.

## Current Scope (Batch 4 Runtime Lifecycle Kernel)

Batch 4 introduces the authoritative application runtime kernel (`jarvis.core.runtime.JarvisApplication`), managing deterministic component lifecycles (`STOPPED` -> `STARTING` -> `INITIALIZING` -> `RUNNING` -> `STOPPING` -> `STOPPED` / `FAILED`), dependency graph resolution, reverse order teardown, signal handling, and status/health inspection.

**Note**: High-level subsystems (Agents, LLM routing, memory, voice, vision, Telegram, system automation, health monitoring watchdog) are **DEFERRED — FUTURE BATCH**.

## Quick Start / Run Kernel

Run the main application entry point:
```powershell
# Execute kernel test run (startup & immediate graceful shutdown)
python main.py --test-run

# Run kernel for 5 seconds
python main.py --duration 5.0
```

## Local Quality Gate

Run full quality validation suite:
```powershell
python scripts/quality_gate.py
```

The script executes:
1. Python compilation (`compileall`)
2. Core & runtime import validation
3. Linter check (`ruff check .`)
4. Formatter check (`ruff format --check .`)
5. Type checking (`mypy main.py config jarvis/core scripts`)
6. Security scan (`bandit -r jarvis/ config/ main.py -q -ll`)
7. Secret scan
8. Tests & coverage (`pytest --cov=jarvis --cov=config --cov-report=term-missing`)

## Test Commands

```powershell
# Run Pytest Suite (74 tests passing)
pytest

# Run Runtime Kernel Tests
pytest tests/unit/test_runtime.py
```

