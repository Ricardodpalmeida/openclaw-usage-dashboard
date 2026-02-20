"""
Tool calls provider — parses tool usage from OpenClaw session JSONL files.

API endpoint : Not applicable — log parsing only
Auth         : None required (uses session files)
Method       : Session JSONL parsing via app/log_parser.py parse_tool_calls()
Tracks       : web_search, browser, exec, read/write/edit, image, etc.

This provider tracks API calls to external services like Brave Search,
browser automation, and internal tool usage.
"""

import logging
import os
from typing import List

from ..log_parser import parse_tool_calls
from .base_provider import BaseProvider, UsageRecord

logger = logging.getLogger(__name__)


class ToolProvider(BaseProvider):
    name = "tools"
    display_name = "Tool Calls"

    def is_configured(self) -> bool:
        # Always enabled — no API key required
        return True

    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Parse OpenClaw session files for tool call usage."""
        raw = parse_tool_calls(
            start_date=start_date,
            end_date=end_date,
        )
        records = [
            UsageRecord(
                provider=r["provider"],
                model=r["tool_name"],  # Store tool_name in model field
                date=r["date"],
                hour=r["hour"],
                input_tokens=0,  # Not applicable for tool calls
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                real_tokens=0,
                request_count=r["call_count"],
                estimated_cost_usd=0.0,  # No cost tracking for tools yet
            )
            for r in raw
        ]
        logger.info("ToolProvider: %d tool call records found", len(records))
        return records