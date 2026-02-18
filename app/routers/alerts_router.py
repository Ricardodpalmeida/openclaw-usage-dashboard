"""
Alert API endpoints.

POST /api/alerts/test  — send a test WhatsApp message via OpenClaw Gateway to verify configuration
"""

import logging

from fastapi import APIRouter, HTTPException

from ..alerting import send_whatsapp_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/test")
async def test_alert():
    """Send a test WhatsApp message to verify the alert configuration."""
    ok = await send_whatsapp_alert(
        "✅ OpenClaw Usage Dashboard — test alert working."
    )
    if ok:
        return {"ok": True}
    raise HTTPException(
        status_code=502,
        detail="Failed to send WhatsApp message. Check OPENCLAW_GATEWAY_TOKEN env var.",
    )
