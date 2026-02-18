"""
Google Gemini provider — parses token usage from OpenClaw log files.

API endpoint : None available as of 2026-02
               Google does not expose a Gemini-specific usage API.
Auth         : GEMINI_API_KEY (used only for is_configured detection)
Method       : Log file parsing via app/log_parser.py
Model prefix : "gemini-"
Limitations  : Cost estimation not possible without Google Cloud Billing API.
               Log entries must contain token counts to be included.

TODO — Google Cloud Billing API (future):
  If a Gemini-specific usage API becomes available:
  1. Enable Cloud Billing API in Google Cloud Console
  2. Create a service account with billing.accounts.getUsageExportSchema permission
  3. Use: GET https://cloudbilling.googleapis.com/v1/billingAccounts/{account}/skus
  4. Replace parse_log_for_provider call below with an httpx REST call.

Required env vars:
  GEMINI_API_KEY — used only to indicate the provider is configured
"""

import logging
import os
from typing import List

from .base_provider import BaseProvider, UsageRecord
from ..log_parser import parse_log_for_provider

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    name = "google"
    display_name = "Google Gemini"

    MODEL_PREFIX = "gemini-"

    def is_configured(self) -> bool:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        return bool(key)

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw log file for Gemini model usage."""
        if not self.is_configured():
            logger.warning("GoogleProvider: GEMINI_API_KEY not set — skipping")
            return []

        records = parse_log_for_provider(
            provider_name=self.name,
            model_prefix=self.MODEL_PREFIX,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("GoogleProvider: found %d records from log parsing", len(records))
        return records
