"""
Alert API endpoints.

POST /api/alerts/test  — send a test Telegram message to verify configuration
"""

import logging

from fastapi import APIRouter, HTTPException

from ..alerting import send_telegram_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/test")
async def test_alert():
    """Send a test Telegram message to verify the alert configuration."""
    ok = await send_telegram_alert(
        "✅ OpenClaw Usage Dashboard — test alert working."
    )
    if ok:
        return {"ok": True}
    raise HTTPException(
        status_code=502,
        detail="Failed to send Telegram message. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.",
    )
