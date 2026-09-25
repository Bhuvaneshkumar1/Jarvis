# JARVIS — Personal Autonomous AI Assistant (Windows-First)

```text
Project status:
FOUNDATION / NOT PRODUCTION READY
```

## Purpose

JARVIS is a Windows-first personal autonomous AI assistant engineering project built following strict production guidelines.

## Current Scope (Batch 1 Foundation)

Batch 1 establishes the baseline software repository, directory structure, logging, configuration, exception hierarchy, static analysis tooling, and test infrastructure.

**Note**: High-level subsystems (Agents, LLM routing, memory, voice, vision, Telegram, system automation, health monitoring) are **PLANNED / UNIMPLEMENTED** and will be built in subsequent batches.

## Architecture Overview

```text
User
 ↓
Gateway [PLANNED]
 ↓
Core (Configuration, Logging, Exceptions) [IMPLEMENTED]
 ↓
Planner [PLANNED]
 ↓
Agent Manager [PLANNED]
 ↓
Tools / Memory / LLM [PLANNED]
 ↓
Verification [PLANNED]
 ↓
Audit [PLANNED]
```

## Development Setup

1. **Environment Requirements**:
   - OS: Windows 11
   - Python: 3.12.8

2. **Installation**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .[dev]
   ```

3. **Running Foundation Verification**:
   ```powershell
   python main.py
   ```

## Test Commands

```powershell
# Run Unit & Foundation Test Suite
pytest

# Run Test Coverage
pytest --cov=jarvis --cov=config --cov-report=term-missing

# Run Static Type Checker
mypy main.py config/ jarvis/core/

# Run Linter
ruff check .
```

## Security Rules Baseline

- `.env` contains local secrets and is excluded from Git tracking.
- `.env.example` contains variable names only.
- Daily audit log files automatically sanitize credential patterns.
- No hard-coded credentials or fake placeholder APIs.
