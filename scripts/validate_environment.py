"""
Environment Security & Validation Command Line Tool for JARVIS (Batch 9).
Executes authoritative environment validation, security enforcement, and safe diagnostics output.
Exit codes:
0 -> valid
1 -> validation failure
2 -> security failure
3 -> configuration/environment error
"""

import sys
import logging
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.env_security import (
    validate_environment,
    get_environment_diagnostics,
)
from jarvis.core.exceptions import (
    EnvironmentValidationError,
    EnvironmentSecurityError,
    ConfigurationError,
)


def main() -> int:
    """Loads and validates JARVIS environment, printing safe diagnostic report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        results = validate_environment()
        snapshot = get_environment_diagnostics()
        print(snapshot)
        if results.get("git_warnings"):
            for w in results["git_warnings"]:
                print(f"WARNING: {w}", file=sys.stderr)
        return 0
    except EnvironmentSecurityError as exc:
        print("\nJARVIS ENVIRONMENT SECURITY FAILURE", file=sys.stderr)
        print("====================================", file=sys.stderr)
        print(f"Security Failure: {str(exc)}", file=sys.stderr)
        print("\nRESULT: SECURITY_BLOCKED", file=sys.stderr)
        return 2
    except EnvironmentValidationError as exc:
        print("\nJARVIS ENVIRONMENT VALIDATION FAILURE", file=sys.stderr)
        print("======================================", file=sys.stderr)
        print(f"Validation Failure: {str(exc)}", file=sys.stderr)
        print("\nRESULT: INVALID", file=sys.stderr)
        return 1
    except ConfigurationError as exc:
        print("\nJARVIS CONFIGURATION ERROR", file=sys.stderr)
        print("==========================", file=sys.stderr)
        print(f"Configuration Error: {str(exc)}", file=sys.stderr)
        print("\nRESULT: CONFIG_ERROR", file=sys.stderr)
        return 3
    except Exception as exc:
        print("\nUNEXPECTED ENVIRONMENT ERROR", file=sys.stderr)
        print("============================", file=sys.stderr)
        print(f"Error: {str(exc)}", file=sys.stderr)
        print("\nRESULT: ERROR", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
