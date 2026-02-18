"""
Alert API endpoints.

POST /api/alerts/test  — send a test Telegram message to verify configuration
"""

import logging

from fastapi import APIRouter, HTTPException

from ..database import get_db, get_setting
from ..alerting import send_telegram_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/test")
async def test_alert():
    """Send a test Telegram message to verify the alert configuration."""
    async with get_db() as db:
        enabled = (await get_setting(db, "alert_telegram_enabled", "false")).lower() == "true"
        bot_token = await get_setting(db, "alert_telegram_bot_token", "")
        chat_id = await get_setting(db, "alert_telegram_chat_id", "")

    if not bot_token or not chat_id:
        raise HTTPException(
            status_code=400,
            detail="Telegram bot token and chat ID must be configured before testing.",
        )

    msg = (
        "\u2705 *OpenClaw Alert Test*\n\n"
        "Telegram alerts are configured correctly.\n"
        "You will receive session cost warnings here when costs exceed your threshold."
    )

    ok = await send_telegram_alert(bot_token, chat_id, msg)
    if ok:
        return {"status": "ok", "message": "Test alert sent successfully."}
    else:
        raise HTTPException(
            status_code=502,
            detail="Failed to send Telegram message. Check bot token and chat ID.",
        )
