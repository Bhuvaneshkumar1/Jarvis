"""
JARVIS Quality Gate Validation Runner (Section 20 & 21).
Executes all mandatory CI and local quality checks in deterministic order.
"""

import sys
import os
import re
import subprocess
import time
from typing import List, Tuple, Dict, Any

SECRET_REGEXES = [
    (r"sk-or-v1-[a-zA-Z0-9]{40,}", "OpenRouter Key"),
    (r"ghp_[a-zA-Z0-9]{30,}", "GitHub Personal Access Token"),
    (r"github_pat_[a-zA-Z0-9_]{30,}", "GitHub Fine-Grained Token"),
    (r"xox[bape]-[a-zA-Z0-9\-]{20,}", "Slack Token"),
    (r"cfut_[a-zA-Z0-9]{30,}", "Cloudflare Token"),
    (r"nvapi-[a-zA-Z0-9_]{40,}", "NVIDIA API Key"),
    (r"xai-[a-zA-Z0-9]{40,}", "Grok API Key"),
]

SAFE_PLACEHOLDERS = [
    "YOUR_API_KEY_HERE",
    "CONFIGURED_SECRET",
    "REDACTED",
    "EXAMPLE",
    "TEST_KEY",
    "MOCK",
]


def run_step(name: str, cmd: List[str]) -> Tuple[bool, str]:
    print(f"\n[RUNNING] {name}...")
    start_time = time.time()
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        elapsed = time.time() - start_time
        success = res.returncode == 0
        status_str = f"PASS ({elapsed:.2f}s)" if success else f"FAIL ({elapsed:.2f}s)"
        print(f"[{status_str}] {name}")
        return success, res.stdout
    except Exception as e:
        return False, f"Exception executing step '{name}': {str(e)}"


def run_secret_scan() -> Tuple[bool, str]:
    print("\n[RUNNING] Secret Scan...")
    findings = []
    scanned_files = 0

    # Scan python files and config files, ignoring .env, virtualenv, and test fixtures
    for root, dirs, files in os.walk("."):
        if ".venv" in root or ".git" in root or "__pycache__" in root or ".pytest_cache" in root or "tests" in root:
            continue
        for file in files:
            if file.endswith((".py", ".json", ".toml", ".yaml", ".yml", ".md")) and file != ".env":
                filepath = os.path.join(root, file)
                scanned_files += 1
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for regex, secret_type in SECRET_REGEXES:
                        matches = re.findall(regex, content)
                        for match in matches:
                            if not any(ph in match for ph in SAFE_PLACEHOLDERS):
                                findings.append(f"Potential secret match ({secret_type}) in {filepath}")
                except Exception as ex:
                    findings.append(f"Error reading file {filepath}: {str(ex)}")

    if findings:
        output = "\n".join(findings)
        print("[FAIL] Secret Scan")
        return False, output
    output = f"Scanned {scanned_files} files cleanly. Zero unredacted credentials detected."
    print("[PASS] Secret Scan")
    return True, output


def run_import_validation() -> Tuple[bool, str]:
    print("\n[RUNNING] Import Validation...")
    code = (
        "import main; "
        "import config; "
        "import jarvis; "
        "import jarvis.core; "
        "import jarvis.core.contracts; "
        "import jarvis.core.enums; "
        "print('All core modules imported cleanly.')"
    )
    import_cmd = [sys.executable, "-c", code]
    return run_step("Import Validation", import_cmd)


def main() -> int:
    print("==================================================")
    print("      JARVIS LOCAL QUALITY GATE ENGINE           ")
    print("==================================================")

    steps: List[Tuple[str, Any]] = [
        ("Python Compilation", [sys.executable, "-m", "compileall", "-q", "-x", r"\.venv|\.git|build|dist", "."]),
        ("Import Validation", "CUSTOM_IMPORT"),
        ("Linter Check", [sys.executable, "-m", "ruff", "check", "."]),
        ("Formatter Check", [sys.executable, "-m", "ruff", "format", "--check", "."]),
        ("Type Checking", [sys.executable, "-m", "mypy", "main.py", "config", "jarvis/core"]),
        ("Security Scan", [sys.executable, "-m", "bandit", "-r", "jarvis/", "config/", "main.py", "-q", "-ll"]),
        ("Secret Scan", "CUSTOM_SECRET_SCAN"),
        ("Tests & Coverage", [sys.executable, "-m", "pytest", "--cov=jarvis", "--cov=config", "--cov-report=term-missing"]),
    ]

    results: Dict[str, Tuple[bool, str]] = {}
    all_passed = True

    for step_name, step_cmd in steps:
        if step_cmd == "CUSTOM_IMPORT":
            passed, output = run_import_validation()
        elif step_cmd == "CUSTOM_SECRET_SCAN":
            passed, output = run_secret_scan()
        else:
            passed, output = run_step(step_name, step_cmd)

        results[step_name] = (passed, output)
        if not passed:
            all_passed = False

    print("\n==================================================")
    print("           QUALITY GATE SUMMARY REPORT            ")
    print("==================================================")
    for step_name, (passed, output) in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status:8} {step_name}")

    if not all_passed:
        print("\n[BLOCKERS / DETAILED FAILURE LOGS]")
        for step_name, (passed, output) in results.items():
            if not passed:
                print(f"\n--- Failure Details for '{step_name}' ---")
                print(output)
        print("\nRESULT: FAIL")
        return 1

    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
