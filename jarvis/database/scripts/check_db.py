"""
Database Integrity Check Script (Batch 16).
Usage: python -m jarvis.database.scripts.check_db
"""

import sys
from jarvis.database.settings import get_database_settings
from jarvis.database.health import DatabaseHealthCheck


def main() -> int:
    try:
        settings = get_database_settings()
        checker = DatabaseHealthCheck(settings=settings)
        health = checker.check_health()
        if health.status.value == "HEALTHY":
            print(f"[PASS] Database integrity check PASSED for '{settings.resolve_db_path()}'.")
            return 0
        else:
            print(f"[FAIL] Database integrity check FAILED: {health.error}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"[ERROR] Database integrity check encountered error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
