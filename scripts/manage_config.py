"""
Configuration Management CLI Tool for JARVIS (Batch 11).
Provides safe CLI commands for validating configuration, displaying status, and computing fingerprints.
Exit codes:
0 -> valid / success
1 -> configuration validation failure
2 -> security failure
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from config.hardening import (
    enforce_fail_closed_startup,
    compute_config_fingerprint,
)
from jarvis.core.exceptions import (
    ConfigurationError,
    EnvironmentValidationError,
    EnvironmentSecurityError,
)


def cmd_validate(args: argparse.Namespace) -> int:
    """Executes full fail-closed configuration & environment security validation."""
    settings = get_settings(force_reload=True)
    res = enforce_fail_closed_startup(settings_obj=settings)
    print("JARVIS CONFIGURATION SECURITY VALIDATION")
    print("========================================")
    print(f"Environment: {settings.app.environment.value}")
    print("Configuration: VALID")
    print("Environment Security: VALID")
    print("Secrets Boundary: VALID")
    print(f"Configuration Fingerprint: {res['fingerprint']}")

    if res.get("warnings"):
        print("\nWarnings:")
        for w in res["warnings"]:
            print(f"  - {w}")

    print("\nRESULT: VALID")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Displays safe diagnostic snapshot of active configuration."""
    settings = get_settings(force_reload=True)
    print(settings.get_diagnostics_snapshot())
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    """Computes and prints SHA-256 fingerprint of current configuration."""
    settings = get_settings(force_reload=True)
    fp = compute_config_fingerprint(settings)
    print("JARVIS CONFIGURATION FINGERPRINT")
    print("================================")
    print(f"Fingerprint (SHA-256): {fp}")
    return 0


def main() -> int:
    """CLI entry point for configuration manager."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="JARVIS Configuration Security CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Configuration management subcommand")

    # Validate subcommand
    p_val = subparsers.add_parser("validate", help="Execute fail-closed security validation")
    p_val.set_defaults(func=cmd_validate)

    # Status subcommand
    p_status = subparsers.add_parser("status", help="Display safe configuration snapshot")
    p_status.set_defaults(func=cmd_status)

    # Fingerprint subcommand
    p_fp = subparsers.add_parser("fingerprint", help="Compute non-sensitive configuration fingerprint")
    p_fp.set_defaults(func=cmd_fingerprint)

    args = parser.parse_args()

    if not args.subcommand:
        # Default to validate if no subcommand supplied
        return cmd_validate(args)

    try:
        return args.func(args)
    except EnvironmentSecurityError as exc:
        print(f"\nSECURITY FAILURE: {str(exc)}", file=sys.stderr)
        print("\nRESULT: SECURITY_BLOCKED", file=sys.stderr)
        return 2
    except (EnvironmentValidationError, ConfigurationError) as exc:
        print(f"\nVALIDATION FAILURE: {str(exc)}", file=sys.stderr)
        print("\nRESULT: INVALID", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nUNEXPECTED CONFIGURATION ERROR: {str(exc)}", file=sys.stderr)
        print("\nRESULT: ERROR", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
