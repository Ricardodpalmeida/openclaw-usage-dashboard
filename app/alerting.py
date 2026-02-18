"""
Session cost alerting — sends Telegram messages when session cost exceeds threshold.
No LLM involved. Direct HTTP call to Telegram Bot API.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("Telegram alert failed: %s", exc)
        return False


async def check_and_alert(db) -> dict:
    """
    Check current session cost against threshold and send alert if needed.
    Returns a dict describing what happened.
    """
    from .database import get_setting, set_setting
    from .routers.usage_router import get_current_session_data

    # Load settings
    enabled = (await get_setting(db, "alert_telegram_enabled", "false")).lower() == "true"
    if not enabled:
        return {"status": "disabled"}

    bot_token = await get_setting(db, "alert_telegram_bot_token", "")
    chat_id = await get_setting(db, "alert_telegram_chat_id", "")
    if not bot_token or not chat_id:
        return {"status": "not_configured"}

    # Get current session data
    session = await get_current_session_data(db)
    if session.get("status") == "no_active_session":
        return {"status": "no_session"}

    if not session.get("warning"):
        return {"status": "ok", "cost": session.get("estimated_cost_usd")}

    # Check if we already alerted for this session
    last_alerted = await get_setting(db, "alert_last_session_id", "")
    session_id = session.get("session_id", "")
    if last_alerted == session_id:
        return {"status": "already_alerted", "session_id": session_id}

    # Build and send alert message
    threshold = session.get("warning_threshold_usd", 5.0)
    cost = session.get("estimated_cost_usd", 0)
    duration = session.get("duration_minutes", 0)
    models = ", ".join(session.get("models_used", [])) or "unknown"
    msg = (
        f"\u26a0\ufe0f *OpenClaw Session Cost Alert*\n\n"
        f"Session cost has exceeded the ${threshold:.2f} threshold.\n\n"
        f"*Current cost:* ${cost:.2f}\n"
        f"*Models:* {models}\n"
        f"*Duration:* {duration}m\n"
        f"*Messages:* {session.get('message_count', 0)}\n\n"
        f"Consider running `/new` to start a fresh session."
    )

    ok = await send_telegram_alert(bot_token, chat_id, msg)
    if ok:
        await set_setting(db, "alert_last_session_id", session_id)
        await db.commit()
        return {"status": "alerted", "cost": cost}
    else:
        return {"status": "alert_failed"}
