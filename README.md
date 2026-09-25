# JARVIS — Personal Autonomous AI Assistant (Windows-First)

```text
Project status:
EVENT BUS & MESSAGING BASELINE / NOT PRODUCTION READY
```

## Purpose

JARVIS is a Windows-first personal autonomous AI assistant engineering project built following strict production guidelines.

## Current Scope (Batch 5 Internal Event Bus & Messaging)

Batch 5 introduces the authoritative internal event bus (`jarvis.core.events.EventBus`), providing typed event publishing/subscribing, async worker queues with priority-based ordering, handler error isolation, retries with exponential backoff, timeout handling, secret redaction, and runtime kernel lifecycle integration.

**MCP Exclusion Check**: MCP implementation added: **NO** (Strictly excluded).

## Local Quality Gate

Run full quality validation suite:
```powershell
python scripts/quality_gate.py
```

The script executes:
1. Python compilation (`compileall`)
2. Core, runtime & event bus import validation
3. Linter check (`ruff check .`)
4. Formatter check (`ruff format --check .`)
5. Type checking (`mypy main.py config jarvis/core scripts`)
6. Security scan (`bandit -r jarvis/ config/ main.py -q -ll`)
7. Secret scan
8. Tests & coverage (`pytest --cov=jarvis --cov=config --cov-report=term-missing`)

## Test & Benchmark Commands

```powershell
# Run Pytest Suite (89 tests passing)
pytest

# Run Event Bus Unit & Negative Tests
pytest tests/unit/test_event_bus.py

# Run Event Bus Throughput Benchmark
pytest tests/unit/test_event_bus_performance.py -s
```


