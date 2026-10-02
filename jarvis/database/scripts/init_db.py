"""
Database Initialization Script (Batch 16).
Usage: python -m jarvis.database.scripts.init_db
"""

import sys
import asyncio
from jarvis.database.manager import DatabaseManager
from jarvis.database.settings import get_database_settings
from jarvis.core.runtime.context import RuntimeContext


async def main() -> int:
    try:
        settings = get_database_settings()
        mgr = DatabaseManager(settings=settings)
        ctx = RuntimeContext(environment="production")
        await mgr.initialize(ctx)
        await mgr.start()
        print(f"[SUCCESS] Database initialized safely at '{settings.resolve_db_path()}'.")
        await mgr.stop()
        return 0
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
