# JARVIS — Personal Autonomous AI Assistant (Windows-First)

```text
Project status:
FOUNDATION / NOT PRODUCTION READY
```

## Purpose

JARVIS is a Windows-first personal autonomous AI assistant engineering project built following strict production guidelines.

## Current Scope (Batch 3 CI & Quality Baseline)

Batch 3 establishes automated local quality gates (`scripts/quality_gate.py`), GitHub Actions CI pipeline (`.github/workflows/ci.yml`), security static analysis (`bandit`), secret scanning, Python compilation checks, import validation, and contract regression tests.

**Note**: High-level subsystems (Agents, LLM routing, memory, voice, vision, Telegram, system automation, health monitoring) are **DEFERRED — FUTURE BATCH**.

## Local Quality Gate

Run full quality validation suite:
```powershell
python scripts/quality_gate.py
```

The script executes:
1. Python compilation (`compileall`)
2. Core import validation
3. Linter check (`ruff check .`)
4. Formatter check (`ruff format --check .`)
5. Type checking (`mypy main.py config jarvis/core`)
6. Security scan (`bandit -r jarvis/ config/ main.py -q -ll`)
7. Secret scan
8. Tests & coverage (`pytest --cov=jarvis --cov=config --cov-report=term-missing`)

## Test Commands

```powershell
# Run Pytest Suite
pytest

# Run Test Coverage
pytest --cov=jarvis --cov=config --cov-report=term-missing
```

## Security Rules Baseline

- `.env` contains local secrets and is excluded from Git tracking.
- `.env.example` contains variable names only.
- Automated secret detection blocks accidental secret commits.
- Daily audit log files automatically sanitize credential patterns.
