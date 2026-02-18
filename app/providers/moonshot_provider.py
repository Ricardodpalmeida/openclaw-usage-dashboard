"""
Moonshot/Kimi provider — parses token usage from OpenClaw session JSONL files.

API endpoint : No public usage API confirmed as of 2026-02.
               https://api.moonshot.ai does not expose a /v1/usage endpoint.
Auth         : MOONSHOT_API_KEY (used only for is_configured detection)
Method       : Session JSONL parsing via app/log_parser.py
Model prefix : "kimi-", "moonshot-"  (both matched)

TODO — Moonshot Usage API (future):
  If Moonshot publishes a usage API:
  1. Check https://platform.moonshot.ai/docs for /v1/usage or /v1/billing endpoints
  2. Auth likely uses Bearer token with MOONSHOT_API_KEY
  3. Replace parse_sessions call below with an httpx REST call.

Required env vars:
  MOONSHOT_API_KEY — used only to indicate the provider is configured.
"""

import logging
import os
from typing import List

from ..log_parser import parse_sessions
from .base_provider import BaseProvider, UsageRecord

logger = logging.getLogger(__name__)


class MoonshotProvider(BaseProvider):
    name = "moonshot"
    display_name = "Moonshot / Kimi"
    # Models appear as "kimi-k2.5", "kimi-k2-thinking", etc.
    MODEL_PREFIXES = ["kimi-", "moonshot-"]

    def is_configured(self) -> bool:
        return bool(os.getenv("MOONSHOT_API_KEY", "").strip())

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw session files for Moonshot/Kimi model usage."""
        if not self.is_configured():
            logger.warning("MoonshotProvider: MOONSHOT_API_KEY not set — skipping")
            return []

        raw = parse_sessions(
            model_prefixes=self.MODEL_PREFIXES,
            start_date=start_date,
            end_date=end_date,
        )
        records = [
            UsageRecord(
                provider=r["provider"],
                model=r["model"],
                date=r["date"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                total_tokens=r["total_tokens"],
                request_count=r["request_count"],
                estimated_cost_usd=r["estimated_cost_usd"],
            )
            for r in raw
        ]
        logger.info("MoonshotProvider: %d usage records found", len(records))
        return records
