"""
Google Gemini provider — parses token usage from OpenClaw session JSONL files.

API endpoint : None available as of 2026-02.
               Google does not expose a Gemini-specific usage API.
Auth         : GEMINI_API_KEY (used only for is_configured detection)
Method       : Session JSONL parsing via app/log_parser.py
Model prefix : "gemini-"

TODO — Google Cloud Billing API (future):
  If a Gemini-specific usage API becomes available:
  1. Enable Cloud Billing API in Google Cloud Console
  2. Create a service account with billing.accounts.getUsageExportSchema permission
  3. Use: GET https://cloudbilling.googleapis.com/v1/billingAccounts/{account}/skus
  4. Replace parse_sessions call below with an httpx REST call.

Required env vars:
  GEMINI_API_KEY — used only to indicate the provider is configured.
"""

import logging
import os
from typing import List

from ..log_parser import parse_sessions
from .base_provider import BaseProvider, UsageRecord

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    name = "google"
    display_name = "Google Gemini"
    MODEL_PREFIXES = ["gemini-"]

    def is_configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw session files for Gemini model usage."""
        if not self.is_configured():
            logger.warning("GoogleProvider: GEMINI_API_KEY not set — skipping")
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
                hour=r["hour"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                cache_read_tokens=r["cache_read_tokens"],
                real_tokens=r["real_tokens"],
                request_count=r["request_count"],
                estimated_cost_usd=r["estimated_cost_usd"],
            )
            for r in raw
        ]
        logger.info("GoogleProvider: %d usage records found", len(records))
        return records
