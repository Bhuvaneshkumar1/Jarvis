# JARVIS Development Environment Guide — Batch 1

## Prerequisites & Environment Setup

- **Target OS**: Windows 11 (Windows-First)
- **Python Version**: Python 3.12.8

### Setup Steps:

1. **Activate Virtual Environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install Editable Package & Dependencies**:
   ```powershell
   python -m pip install -e .[dev]
   ```

3. **Verify Environment Variables**:
   Copy `.env.example` to `.env` if not present. `.env` is ignored by Git.

4. **Run System Startup Check**:
   ```powershell
   python main.py
   ```
