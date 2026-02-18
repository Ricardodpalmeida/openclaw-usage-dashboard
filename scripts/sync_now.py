#!/usr/bin/env python3
"""
Manual sync trigger — runs outside the FastAPI app.

Usage:
    python scripts/sync_now.py [--days 30] [--provider anthropic|google|moonshot]

Reads the same .env and database path as the main app.
Useful for testing providers or forcing an out-of-cycle refresh.
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Manual OpenClaw usage sync")
    parser.add_argument("--days",     type=int, default=30, help="Number of past days to sync (default: 30)")
    parser.add_argument("--provider", type=str, default=None, help="Specific provider name (default: all)")
    args = parser.parse_args()

    from app.database import init_db
    from app.scheduler import sync_all, sync_provider
    from app.providers import ALL_PROVIDERS

    await init_db()

    end_date   = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.days)).isoformat()

    if args.provider:
        known = [p.name for p in ALL_PROVIDERS]
        if args.provider not in known:
            logger.error("Unknown provider '%s'. Valid options: %s", args.provider, ", ".join(known))
            sys.exit(1)
        logger.info("Syncing provider '%s' from %s to %s", args.provider, start_date, end_date)
        result = await sync_provider(args.provider, start_date, end_date)
        logger.info("Result: %s", result)
    else:
        logger.info("Syncing all providers from %s to %s", start_date, end_date)
        await sync_all()

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
