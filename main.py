"""
JARVIS AI OS — Batch 1 Foundation Entry Point.
Initializes system configuration, logging, and startup validation. Exits cleanly.
"""

import sys
import os
from config.settings import get_settings
from jarvis.core.logging import JarvisLogger
from jarvis.core.exceptions import JarvisError

def main() -> int:
    try:
        # 1. Initialize Configuration
        settings = get_settings()

        # 2. Initialize Logging
        logger = JarvisLogger(component="Main", log_dir=settings.log_dir)
        logger.info("Initializing JARVIS Engineering Foundation Baseline...")

        # 3. Perform Startup Validation
        required_dirs = [settings.log_dir, "data", "config"]
        for d in required_dirs:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
                logger.info(f"Created required directory: {d}")

        summary = settings.get_sanitized_summary()
        logger.info(f"Configuration loaded cleanly: {summary}")

        # 4. Report foundation initialization success
        print("==================================================")
        print("JARVIS ENGINEERING FOUNDATION INITIALIZED CLEANLY")
        print("Status: FOUNDATION BASELINE / NOT PRODUCTION READY")
        print(f"Environment: {settings.env} | Host: {settings.host}:{settings.port}")
        print("==================================================")

        # 5. Exit cleanly
        return 0

    except JarvisError as e:
        print(f"JARVIS Initialization Error: {str(e)}", file=sys.stderr)
        return 1
    except Exception as ex:
        print(f"Unexpected Fatal Error during startup: {str(ex)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
