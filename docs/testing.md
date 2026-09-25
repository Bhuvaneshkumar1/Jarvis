# JARVIS Testing Guide — Batch 1

## Testing Framework & Requirements

Tests are organized under the `tests/` directory:

```text
tests/
├── unit/
├── integration/
├── e2e/
├── security/
├── performance/
└── fixtures/
```

## Running Tests

Run full test suite:
```powershell
pytest
```

Run test suite with coverage:
```powershell
pytest --cov=jarvis --cov=config --cov-report=term-missing
```

Run static type check:
```powershell
mypy main.py config/ jarvis/core/
```

Run linter check:
```powershell
ruff check .
```
