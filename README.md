# JARVIS — Personal Autonomous AI Assistant (Windows-First)

Production-grade autonomous AI assistant for Windows built strictly adhering to the Master Engineering Control Directive.

## Installation & Setup

1. **Clone repository & navigate to root directory**:
   ```powershell
   cd d:\jarvis_v2
   ```

2. **Activate Virtual Environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install Package & Dependencies**:
   ```powershell
   python -m pip install -e .[dev]
   ```

4. **Environment Variables**:
   Copy `.env.example` to `.env` and fill in local configuration values.
   ```powershell
   cp .env.example .env
   ```

## Running Tests

Execute full test suite with coverage:
```powershell
.\.venv\Scripts\pytest --cov=jarvis --cov-report=term-missing
```

## Evidence & Verification

Refer to `EVIDENCE_BATCH_1.md` for batch status, test logs, execution evidence, and negative path verification reports.
