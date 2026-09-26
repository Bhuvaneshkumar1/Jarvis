"""
Configuration Validation Command Line Tool for JARVIS (Batch 8).
Executes authoritative configuration loading, validation, and safe diagnostics output.
"""

import sys
import logging
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from jarvis.core.exceptions import ConfigurationError


def main() -> int:
    """Loads and validates JARVIS configuration, printing safe diagnostic report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        settings = get_settings(force_reload=True)
        snapshot = settings.get_diagnostics_snapshot()
        print(snapshot)
        return 0
    except ConfigurationError as exc:
        print("\nJARVIS CONFIGURATION ERROR", file=sys.stderr)
        print("==========================", file=sys.stderr)
        print(f"Validation Failure: {str(exc)}", file=sys.stderr)
        print("\nRESULT: INVALID", file=sys.stderr)
        return 1
    except Exception as exc:
        print("\nUNEXPECTED CONFIGURATION ERROR", file=sys.stderr)
        print("===============================", file=sys.stderr)
        print(f"Error: {str(exc)}", file=sys.stderr)
        print("\nRESULT: INVALID", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
