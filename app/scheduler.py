"""
APScheduler integration — periodic provider sync.

Schedule:
  - On startup: sync all configured providers for last 30 days
  - Recurring: every SYNC_INTERVAL_HOURS hours (default 6)

Each sync run:
  1. Calls provider.fetch_usage(start_date, end_date)
  2. Upserts returned records into usage_records table
  3. Logs outcome to sync_log table
"""

import logging
import os
from datetime import date, timedelta, timezone, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import get_db, upsert_usage_record, insert_sync_log
from .providers import ALL_PROVIDERS

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def sync_provider(provider_name: str, start_date: str, end_date: str) -> dict:
    """Run a single provider sync and persist results. Returns a status dict."""
    provider = next((p for p in ALL_PROVIDERS if p.name == provider_name), None)
    if provider is None:
        return {"status": "error", "message": f"Unknown provider: {provider_name}"}

    if not provider.is_configured():
        msg = f"{provider.display_name}: not configured — skipping"
        logger.info(msg)
        return {"status": "skipped", "message": msg}

    synced_at = _now_iso()
    try:
        records = await provider.fetch_usage(start_date, end_date)
    except Exception as exc:
        msg = f"{provider.display_name}: fetch failed — {exc}"
        logger.error(msg)
        async with get_db() as db:
            await insert_sync_log(db, provider_name, "error", str(exc)[:500], synced_at)
            await db.commit()
        return {"status": "error", "message": msg}

    async with get_db() as db:
        for rec in records:
            await upsert_usage_record(db, {
                "provider":           rec.provider,
                "model":              rec.model,
                "date":               rec.date,
                "input_tokens":       rec.input_tokens,
                "output_tokens":      rec.output_tokens,
                "total_tokens":       rec.total_tokens,
                "request_count":      rec.request_count,
                "estimated_cost_usd": rec.estimated_cost_usd,
                "synced_at":          synced_at,
            })
        await insert_sync_log(db, provider_name, "ok", f"{len(records)} records upserted", synced_at)
        await db.commit()

    logger.info("%s: synced %d records", provider.display_name, len(records))
    return {"status": "ok", "records": len(records)}


async def sync_all() -> None:
    """Sync all configured providers for the last 30 days."""
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=30)).isoformat()
    logger.info("Starting full sync: %s → %s", start_date, end_date)

    for provider in ALL_PROVIDERS:
        await sync_provider(provider.name, start_date, end_date)

    logger.info("Full sync complete")


def start_scheduler() -> None:
    """Register recurring job and start the scheduler."""
    interval_hours = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))

    scheduler.add_job(
        sync_all,
        trigger="interval",
        hours=interval_hours,
        id="sync_all",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — syncing every %d hour(s)", interval_hours)
