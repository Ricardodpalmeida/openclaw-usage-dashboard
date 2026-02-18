"""
Anthropic provider — parses token usage from OpenClaw log files.

API endpoint : Not available for individual/Pro accounts.
               The Anthropic Admin API (/v1/organizations/usage) requires a
               Team or Enterprise plan. For individual accounts, the OpenClaw
               log file is the only source of usage data.
Auth         : ANTHROPIC_API_KEY (used only for is_configured detection)
Method       : Log file parsing via app/log_parser.py
Model prefix : "claude-"
Limitations  : Cost estimation not possible from logs alone (no billing data).
               Cached token breakdowns may not be available in log entries.

Future REST API support:
  If Anthropic ever releases a usage API accessible to individual accounts,
  or if you upgrade to a Team/Enterprise plan:
  1. Generate an Admin Key at console.anthropic.com → API Keys → Admin Keys
  2. Set ANTHROPIC_ADMIN_KEY env var
  3. Implement a REST fetch in this file that calls:
       GET https://api.anthropic.com/v1/organizations/usage
       Headers: x-api-key: {ANTHROPIC_ADMIN_KEY}, anthropic-version: 2023-06-01
       Params:  start_time, end_time (ISO 8601), group_by=model
  4. Use ANTHROPIC_ADMIN_KEY as the gate: if set → use API, else → fall back to log parsing.

Required env vars:
  ANTHROPIC_API_KEY — same key used by OpenClaw; used only to detect configuration
"""

import logging
import os
from typing import List

from .base_provider import BaseProvider, UsageRecord
from ..log_parser import parse_log_for_provider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    display_name = "Anthropic"

    MODEL_PREFIX = "claude-"

    def is_configured(self) -> bool:
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        return bool(key)

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw log file for Claude model usage."""
        if not self.is_configured():
            logger.warning("AnthropicProvider: ANTHROPIC_API_KEY not set — skipping")
            return []

        records = parse_log_for_provider(
            provider_name=self.name,
            model_prefix=self.MODEL_PREFIX,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("AnthropicProvider: found %d records from log parsing", len(records))
        return records
