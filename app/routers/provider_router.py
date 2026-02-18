"""
Provider and sync API endpoints.

GET  /api/providers       — list all providers with configured status
POST /api/sync            — trigger a manual sync for all configured providers
GET  /api/sync/log        — last 20 sync events
"""

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter

from ..database import get_db
from ..models import ProviderStatus, SyncLogEntry, SyncResult
from ..providers import ALL_PROVIDERS
from ..scheduler import sync_all

router = APIRouter(tags=["providers"])


@router.get("/api/providers", response_model=List[ProviderStatus])
async def list_providers():
    """Return all registered providers with their configuration status."""
    return [
        ProviderStatus(
            name=p.name,
            display_name=p.display_name,
            is_configured=p.is_configured(),
            method="Log parser (~/.openclaw/logs/openclaw.log)",
        )
        for p in ALL_PROVIDERS
    ]


@router.post("/api/sync", response_model=SyncResult)
async def trigger_sync():
    """Manually trigger a full sync across all configured providers."""
    configured = [p.name for p in ALL_PROVIDERS if p.is_configured()]
    await sync_all()
    return SyncResult(
        triggered=True,
        providers_synced=configured,
        message=f"Sync complete for {len(configured)} provider(s): {', '.join(configured) or 'none'}",
    )


@router.get("/api/sync/log", response_model=List[SyncLogEntry])
async def get_sync_log():
    """Return the last 20 sync events."""
    async with await get_db() as db:
        rows = await (await db.execute(
            "SELECT id, provider, status, message, synced_at "
            "FROM sync_log ORDER BY id DESC LIMIT 20"
        )).fetchall()

    return [
        SyncLogEntry(
            id=r["id"],
            provider=r["provider"],
            status=r["status"],
            message=r["message"],
            synced_at=r["synced_at"],
        )
        for r in rows
    ]
