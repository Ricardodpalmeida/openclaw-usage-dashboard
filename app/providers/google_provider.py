"""
Google Gemini provider — parses token usage from OpenClaw session JSONL files.

API endpoint : None available.
               Google does not expose a Gemini-specific usage API.
Auth         : GEMINI_API_KEY (used only for is_configured detection)
Method       : Session JSONL parsing via app/log_parser.py
Model prefix : "gemini-"

⚠ WHY GEMINI USAGE IS NOT CAPTURED:
  OpenClaw uses Gemini exclusively in heartbeat calls. Heartbeat calls do NOT
  create session JSONL files — only interactive sessions and sub-agent runs do.
  Since this dashboard sources all data from session JSONL files, Gemini usage
  is effectively invisible. The provider is configured but produces zero records.
  This is a fundamental limitation of the log-based approach: if a model is only
  used in contexts that do not produce JSONL files, it cannot be tracked.

  To track Gemini in the future, one of the following approaches would be needed:
    a) OpenClaw starts writing heartbeat usage to a separate log file.
    b) Google exposes a Gemini usage API (Google Cloud Billing API covers spend
       but not per-model token counts at this time).
    c) A sidecar proxy intercepts Gemini API calls and logs them independently.

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
                cache_write_tokens=r["cache_write_tokens"],
                real_tokens=r["real_tokens"],
                request_count=r["request_count"],
                estimated_cost_usd=r["estimated_cost_usd"],
            )
            for r in raw
        ]
        logger.info("GoogleProvider: %d usage records found", len(records))
        return records
