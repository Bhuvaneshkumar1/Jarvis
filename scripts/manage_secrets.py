"""
Secrets Management Command Line Tool for JARVIS (Batch 10).
Provides safe CLI inspection, master key initialization, credential format validation, and rotation.
Exit codes:
0 -> success
1 -> operation error
2 -> security failure
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.core.exceptions import ConfigurationError, EnvironmentSecurityError, AuthorizationError
from jarvis.core.secrets.crypto import MasterKeyManager
from jarvis.core.secrets.manager import get_secrets_manager


def cmd_status(args: argparse.Namespace) -> int:
    """Prints safe diagnostics snapshot without exposing secrets."""
    mgr = get_secrets_manager()
    print(mgr.get_diagnostics_snapshot())
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Lists safe inventory metadata without exposing secrets."""
    mgr = get_secrets_manager()
    inv = mgr.get_sanitized_inventory()
    print("JARVIS SECRET INVENTORY")
    print("=======================")
    if not inv:
        print("No secrets currently managed.")
        return 0

    for k, v in inv.items():
        print(f"\n{k}:")
        print(f"  source: {v['source']}")
        print(f"  classification: {v['classification']}")
        print(f"  version: {v['version']}")
        print(f"  fingerprint: {v['fingerprint'][:12]}...")
        print(f"  present: {'yes' if v['present'] else 'no'}")
        print(f"  valid_format: {'yes' if v['valid_format'] else 'no'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validates presence and format of all credentials."""
    mgr = get_secrets_manager()
    val_map = mgr.validate_credentials()
    print("CREDENTIAL VALIDATION REPORT")
    print("============================")
    all_valid = True
    for k, res in val_map.items():
        status_str = "VALID" if res.valid else "INVALID"
        if not res.valid:
            all_valid = False
        print(f"  {k}: {status_str}")
        if res.reasons:
            for r in res.reasons:
                print(f"    - {r}")

    if all_valid:
        print("\nRESULT: ALL CREDENTIALS VALID")
        return 0
    else:
        print("\nRESULT: CREDENTIAL VALIDATION ISSUES DETECTED")
        return 1


def cmd_init_key(args: argparse.Namespace) -> int:
    """Generates master key file if missing."""
    key_path = Path("data/secrets/master.key")
    if key_path.exists() and not args.force:
        print(f"Master key file already exists at '{key_path}'. Use --force to overwrite.", file=sys.stderr)
        return 1

    MasterKeyManager.initialize_key_file(key_path)
    print(f"Master key initialized and stored securely at '{key_path}'.")
    print("Fingerprint: OK")
    return 0


def main() -> int:
    """CLI entry point for secrets manager."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="JARVIS Secrets Management CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Secrets management subcommand")

    # Status subcommand
    p_status = subparsers.add_parser("status", help="Display safe diagnostics snapshot")
    p_status.set_defaults(func=cmd_status)

    # List subcommand
    p_list = subparsers.add_parser("list", help="List safe metadata inventory")
    p_list.set_defaults(func=cmd_list)

    # Validate subcommand
    p_val = subparsers.add_parser("validate", help="Validate credential formats")
    p_val.set_defaults(func=cmd_validate)

    # Init Key subcommand
    p_init = subparsers.add_parser("init-key", help="Initialize master encryption key file")
    p_init.add_argument("--force", action="store_true", help="Force overwrite existing key")
    p_init.set_defaults(func=cmd_init_key)

    args = parser.parse_args()

    if not args.subcommand:
        # Default to status if no subcommand provided
        return cmd_status(args)

    try:
        return args.func(args)
    except EnvironmentSecurityError as exc:
        print(f"\nSECURITY FAILURE: {str(exc)}", file=sys.stderr)
        return 2
    except (ConfigurationError, AuthorizationError) as exc:
        print(f"\nERROR: {str(exc)}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nUNEXPECTED ERROR: {str(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
