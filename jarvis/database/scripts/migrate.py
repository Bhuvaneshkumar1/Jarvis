"""
Database Migration Script (Batch 16).
Usage: python -m jarvis.database.scripts.migrate
"""

import sys
from jarvis.database.settings import get_database_settings
from jarvis.database.connection import connection_scope
from jarvis.database.migrations.runner import MigrationRunner


def main() -> int:
    try:
        settings = get_database_settings()
        runner = MigrationRunner(settings=settings)
        with connection_scope(settings) as conn:
            applied = runner.discover_and_apply_pending(conn)
            print(f"[SUCCESS] Migrations up-to-date. Applied: {applied}")
        return 0
    except Exception as e:
        print(f"[ERROR] Migration failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
