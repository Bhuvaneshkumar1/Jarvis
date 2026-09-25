"""
JARVIS AI OS — Main Application Kernel Entry Point.
Constructs and executes the authoritative JarvisApplication runtime.
"""

import sys
import asyncio
import argparse
from typing import Optional
from jarvis.core.runtime import JarvisApplication
from jarvis.core.exceptions import JarvisError


async def run_app(duration: Optional[float] = None) -> int:
    app = JarvisApplication()
    try:
        await app.run_until_shutdown(run_duration=duration)
        status = app.get_status()
        print("==================================================")
        print("JARVIS APPLICATION RUNTIME EXECUTION COMPLETED")
        print(f"State: {status['state']} | Uptime: {status['uptime_seconds']}s")
        print(f"Components Registered: {status['total_components']}")
        print("==================================================")
        return 0
    except JarvisError as e:
        print(f"JARVIS Runtime Error: {str(e)}", file=sys.stderr)
        return 1
    except Exception as ex:
        print(f"Unexpected Fatal Error during runtime execution: {str(ex)}", file=sys.stderr)
        return 1


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS AI OS Application Kernel")
    parser.add_argument(
        "--duration",
        type=float,
        default=0.1,
        help="Run duration in seconds before initiating graceful shutdown",
    )
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Run startup and immediate graceful shutdown",
    )

    if argv is not None:
        parsed_args = parser.parse_args(argv)
    elif len(sys.argv) > 0 and sys.argv[0].endswith("main.py"):
        parsed_args = parser.parse_args(sys.argv[1:])
    else:
        parsed_args = parser.parse_args(["--test-run"])

    run_duration = 0.05 if parsed_args.test_run else parsed_args.duration
    return asyncio.run(run_app(duration=run_duration))


if __name__ == "__main__":
    sys.exit(main())
