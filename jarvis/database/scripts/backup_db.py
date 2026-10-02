"""
Database Online Backup Script (Batch 16).
Usage: python -m jarvis.database.scripts.backup_db
"""

import sys
from jarvis.database.settings import get_database_settings
from jarvis.database.backup import DatabaseBackupManager


def main() -> int:
    try:
        settings = get_database_settings()
        mgr = DatabaseBackupManager(settings=settings)
        path = mgr.create_backup()
        print(f"[SUCCESS] Database backup created and validated at '{path}'.")
        return 0
    except Exception as e:
        print(f"[ERROR] Database backup failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
