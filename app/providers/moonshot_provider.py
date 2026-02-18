"""
Moonshot/Kimi provider — parses token usage from OpenClaw log files.

API endpoint : No public usage API confirmed as of 2026-02.
               https://api.moonshot.ai does not expose a /v1/usage endpoint.
Auth         : MOONSHOT_API_KEY (used only for is_configured detection)
Method       : Log file parsing via app/log_parser.py
Model prefix : "kimi-", "moonshot-"  (both checked)
Limitations  : Cost estimation not possible from logs alone.
               Moonshot pricing not publicly documented in machine-readable form.

TODO — Moonshot Usage API (future):
  If Moonshot publishes a usage API:
  1. Check https://platform.moonshot.ai/docs for /v1/usage or /v1/billing endpoints
  2. Auth likely uses Bearer token with MOONSHOT_API_KEY
  3. Replace parse_log_for_provider call below with an httpx REST call.

Required env vars:
  MOONSHOT_API_KEY — used only to indicate the provider is configured
"""

import logging
import os
from typing import List

from .base_provider import BaseProvider, UsageRecord
from ..log_parser import parse_log_for_provider

logger = logging.getLogger(__name__)


class MoonshotProvider(BaseProvider):
    name = "moonshot"
    display_name = "Moonshot / Kimi"

    # Moonshot models may appear as "kimi-*" or "moonshot-*" in logs
    MODEL_PREFIXES = ["kimi-", "moonshot-"]

    def is_configured(self) -> bool:
        key = os.getenv("MOONSHOT_API_KEY", "").strip()
        return bool(key)

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw log file for Moonshot/Kimi model usage."""
        if not self.is_configured():
            logger.warning("MoonshotProvider: MOONSHOT_API_KEY not set — skipping")
            return []

        all_records: List[UsageRecord] = []
        for prefix in self.MODEL_PREFIXES:
            records = parse_log_for_provider(
                provider_name=self.name,
                model_prefix=prefix,
                start_date=start_date,
                end_date=end_date,
            )
            all_records.extend(records)

        logger.info("MoonshotProvider: found %d records from log parsing", len(all_records))
        return all_records
