"""
Session cost alerting — sends Telegram messages via Bot API.

Architecture:
  Dashboard (Docker) → POST https://api.telegram.org/bot<token>/sendMessage

No LLM involved, no bridge required. Pure outbound HTTPS from the container.

Required env vars:
  TELEGRAM_BOT_TOKEN    Telegram bot token (from @BotFather)
  TELEGRAM_CHAT_ID      Target chat/user ID
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def send_telegram_alert(message: str) -> bool:
    """Send a Telegram message via Bot API. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — alert skipped")
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            )
            data = resp.json()
            if data.get("ok"):
                logger.info("Telegram alert sent to chat %s", TELEGRAM_CHAT_ID)
                return True
            logger.error("Telegram API error: %s", data)
            return False
    except Exception as exc:
        logger.error("Telegram alert failed: %s", exc)
        return False


async def check_and_alert(db) -> dict:
    """Check current session cost vs threshold and send Telegram alert if needed."""
    from .database import get_setting, set_setting
    from .routers.usage_router import get_current_session_data

    enabled = (await get_setting(db, "alert_telegram_enabled", "false")).lower() == "true"
    if not enabled:
        return {"status": "disabled"}

    session = await get_current_session_data(db)
    if session.get("status") == "no_active_session":
        return {"status": "no_session"}

    cost_warning = session.get("warning", False)
    token_warning = session.get("token_warning", False)
    if not cost_warning and not token_warning:
        return {"status": "ok", "cost": session.get("estimated_cost_usd")}

    last_alerted = await get_setting(db, "alert_last_session_id", "")
    session_id = session.get("session_id", "")
    if last_alerted == session_id:
        return {"status": "already_alerted"}

    threshold = session.get("warning_threshold_usd", 5.0)
    token_threshold = session.get("warning_threshold_tokens", 100000)
    cost = session.get("estimated_cost_usd", 0)
    total_tokens = session.get("total_tokens", 0)
    duration = session.get("duration_minutes", 0)
    models = ", ".join(session.get("models_used", []))
    count = session.get("message_count", 0)

    reasons = []
    if cost_warning:
        reasons.append(f"💰 Cost: ${cost:.2f} (limit ${threshold:.2f})")
    if token_warning:
        reasons.append(f"📏 Context: {total_tokens:,} tokens (limit {token_threshold:,})")

    msg = (
        f"⚠️ OpenClaw session alert\n\n"
        + "\n".join(reasons)
        + f"\n\nModels: {models} | {duration}m | {count} messages\n\n"
        f"Run /new to start a fresh session."
    )

    ok = await send_telegram_alert(msg)
    if ok:
        await set_setting(db, "alert_last_session_id", session_id)
        return {"status": "alerted", "cost": cost}
    return {"status": "alert_failed"}
