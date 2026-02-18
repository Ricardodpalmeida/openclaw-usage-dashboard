"""
Anthropic provider — parses token usage from OpenClaw session JSONL files.

API endpoint : Not available for individual/Pro accounts.
               The Anthropic Admin API (/v1/organizations/usage) requires a
               Team or Enterprise plan. For individual accounts, session JSONL
               files are the only source of usage data.
Auth         : ANTHROPIC_API_KEY (used only for is_configured detection)
Method       : Session JSONL parsing via app/log_parser.py
Model prefix : "claude-"
Limitations  : Cost is zero for Anthropic (pricing not embedded in session files).

Future REST API support:
  If Anthropic ever releases a usage API for individual accounts, or if you
  upgrade to a Team/Enterprise plan:
  1. Generate an Admin Key at console.anthropic.com → API Keys → Admin Keys
  2. Set ANTHROPIC_ADMIN_KEY env var
  3. Implement a REST fetch calling:
       GET https://api.anthropic.com/v1/organizations/usage
       Headers: x-api-key: {ANTHROPIC_ADMIN_KEY}, anthropic-version: 2023-06-01
       Params:  start_time, end_time (ISO 8601), group_by=model
  4. Gate on ANTHROPIC_ADMIN_KEY: if set → use API, else → fall back to session parsing.

Required env vars:
  ANTHROPIC_API_KEY — same key used by OpenClaw; used only to detect configuration.
"""

import logging
import os
from typing import List

from ..log_parser import parse_sessions
from .base_provider import BaseProvider, UsageRecord

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    display_name = "Anthropic"
    MODEL_PREFIXES = ["claude-"]

    def is_configured(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw session files for Claude model usage."""
        if not self.is_configured():
            logger.warning("AnthropicProvider: ANTHROPIC_API_KEY not set — skipping")
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
        logger.info("AnthropicProvider: %d usage records found", len(records))
        return records
