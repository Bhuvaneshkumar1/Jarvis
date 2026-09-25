# JARVIS Development Environment Guide — Batch 5

## Prerequisites & Supported Target Environment

- **OS**: Windows 11 (Windows-First)
- **Supported Python Version**: Python 3.12.8

## Environment Setup

1. **Activate Virtual Environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install Editable Package & Development Dependencies**:
   ```powershell
   python -m pip install -e .[dev]
   ```

3. **Running the Application Kernel & Event Bus**:
   - **Test Run (Startup & Immediate Graceful Shutdown)**:
     ```powershell
     python main.py --test-run
     ```
   - **Timed Run**:
     ```powershell
     python main.py --duration 5.0
     ```

4. **Running Event Bus Benchmark**:
   ```powershell
   pytest tests/unit/test_event_bus_performance.py -s
   ```

5. **Local Quality Gate Runner**:
   Execute the single authoritative local quality gate script to run compilation, import check, linting, format check, type checking, security scanning, secret scanning, and test coverage:
   ```powershell
   python scripts/quality_gate.py
   ```


5. **Individual Validation Commands**:
   - **Compilation**: `python -m compileall -q -x "\.venv|\.git|build|dist" .`
   - **Imports**: `pytest tests/unit/test_imports.py`
   - **Linter**: `ruff check .`
   - **Formatter Check**: `ruff format --check .`
   - **Type Checker**: `mypy main.py config jarvis/core scripts`
   - **Security Scan**: `bandit -r jarvis/ config/ main.py -q -ll`
   - **Tests & Coverage**: `pytest --cov=jarvis --cov=config --cov-report=term-missing`

