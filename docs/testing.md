# JARVIS Testing Guide & CI Baseline — Batch 5

## Test Suite Architecture

The test suite is organized under `tests/`:

```text
tests/
├── unit/
│   ├── test_event_bus.py (Batch 5 Event Bus Pub/Sub & Negative Tests)
│   ├── test_event_bus_performance.py (Batch 5 Event Bus Benchmark)
│   ├── test_runtime.py (Batch 4 Runtime Kernel Lifecycle & Negative Tests)
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_exceptions.py
│   ├── test_imports.py
│   ├── test_compile.py
│   └── contracts/
│       ├── test_requests_contract.py
│       ├── test_tasks_contract.py
│       ├── test_tools_contract.py
│       ├── test_llm_contract.py
│       ├── test_security_audit_health_contracts.py
│       └── test_contract_negative_validation.py
├── integration/
│   └── test_startup.py
├── security/
│   ├── test_secrets_safety.py
│   └── test_secret_scanner.py
├── regression/
└── fixtures/
    └── conftest.py
```

## Running Tests

- **Run Quality Gate**: `python scripts/quality_gate.py`
- **Run Pytest Directly**: `pytest`
- **Run Event Bus Tests**: `pytest tests/unit/test_event_bus.py`
- **Run Event Bus Benchmark**: `pytest tests/unit/test_event_bus_performance.py -s`
- **Run Coverage**: `pytest --cov=jarvis --cov=config --cov-report=term-missing`


## CI Pipeline Reproduction

CI workflow is defined at `.github/workflows/ci.yml`.
To reproduce CI failure locally, run the failing step:
- **Lint failure**: `ruff check .`
- **Format failure**: `ruff format --check .`
- **Type failure**: `mypy main.py config jarvis/core scripts`
- **Security failure**: `bandit -r jarvis/ config/ main.py -q -ll`
- **Secret failure**: `python scripts/quality_gate.py`

