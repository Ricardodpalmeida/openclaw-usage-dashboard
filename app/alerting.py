"""
Session cost alerting — sends WhatsApp via OpenClaw Gateway /tools/invoke.
No LLM involved. Pure HTTP call to the gateway's tool invocation API.

Gateway docs: the /tools/invoke endpoint calls any tool directly with bearer auth.
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)


async def send_whatsapp_alert(message: str) -> bool:
    """Send a WhatsApp message via OpenClaw Gateway. Returns True on success."""
    gateway_url = os.getenv("OPENCLAW_GATEWAY_URL", "http://host.docker.internal:18789")
    token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
    to = os.getenv("WHATSAPP_ALERT_TO", "+351910298749")

    if not token:
        logger.warning("OPENCLAW_GATEWAY_TOKEN not set — WhatsApp alert skipped")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{gateway_url}/tools/invoke",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "tool": "message",
                    "args": {
                        "action": "send",
                        "channel": "whatsapp",
                        "to": to,
                        "message": message,
                    },
                },
            )
            data = resp.json()
            if data.get("ok"):
                logger.info("WhatsApp alert sent successfully")
                return True
            logger.error("Gateway error: %s", data)
            return False
    except Exception as exc:
        logger.error("WhatsApp alert failed: %s", exc)
        return False


async def check_and_alert(db) -> dict:
    """Check session cost vs threshold and send WhatsApp alert if needed."""
    from .database import get_setting, set_setting
    from .routers.usage_router import get_current_session_data

    enabled = (await get_setting(db, "alert_whatsapp_enabled", "false")).lower() == "true"
    if not enabled:
        return {"status": "disabled"}

    session = await get_current_session_data(db)
    if session.get("status") == "no_active_session":
        return {"status": "no_session"}

    if not session.get("warning"):
        return {"status": "ok", "cost": session.get("estimated_cost_usd")}

    last_alerted = await get_setting(db, "alert_last_session_id", "")
    session_id = session.get("session_id", "")
    if last_alerted == session_id:
        return {"status": "already_alerted"}

    threshold = session.get("warning_threshold_usd", 5.0)
    cost = session.get("estimated_cost_usd", 0)
    duration = session.get("duration_minutes", 0)
    models = ", ".join(session.get("models_used", []))
    count = session.get("message_count", 0)

    msg = (
        f"⚠️ OpenClaw session cost alert\n\n"
        f"Current cost: ${cost:.2f} (threshold: ${threshold:.2f})\n"
        f"Models: {models} | {duration}m | {count} messages\n\n"
        f"Run /new to start a fresh session."
    )

    ok = await send_whatsapp_alert(msg)
    if ok:
        await set_setting(db, "alert_last_session_id", session_id)
        return {"status": "alerted", "cost": cost}
    return {"status": "alert_failed"}
