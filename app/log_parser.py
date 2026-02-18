"""
OpenClaw log parser — extracts token usage from openclaw.log.

OpenClaw logs structured JSON lines.  Each line may contain token usage
information for a model call.  This module reads the log file, filters for
lines that match a given model prefix, and aggregates usage by (model, date).

Log path is read from the OPENCLAW_LOG_PATH env var, defaulting to
~/.openclaw/logs/openclaw.log.

As of OpenClaw v2026.2.17, cron run logs also include per-run usage stats
at the same path format — this parser handles both.

Typical log line structure (JSON):
{
  "timestamp": "2026-02-18T10:00:00.000Z",
  "level": "info",
  "model": "gemini-2.0-flash",
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567
  }
}

Or flat structure:
{
  "ts": "2026-02-18T10:00:00Z",
  "model": "gemini-2.0-flash",
  "inputTokens": 1234,
  "outputTokens": 567
}
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .providers.base_provider import UsageRecord

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = "~/.openclaw/logs/openclaw.log"


def _get_log_path() -> Path:
    raw = os.getenv("OPENCLAW_LOG_PATH", DEFAULT_LOG_PATH)
    return Path(raw).expanduser().resolve()


def _extract_date(line_data: dict) -> str | None:
    """Extract ISO date (YYYY-MM-DD) from a log entry dict."""
    for key in ("timestamp", "ts", "time", "date", "@timestamp"):
        val = line_data.get(key)
        if val and isinstance(val, str):
            try:
                # Handle both "2026-02-18T..." and "2026-02-18 ..."
                dt_str = val[:19].replace(" ", "T")
                dt = datetime.fromisoformat(dt_str)
                return dt.date().isoformat()
            except ValueError:
                pass
    return None


def _extract_tokens(line_data: dict) -> Tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a log entry dict."""
    # Nested usage object
    usage = line_data.get("usage", {})
    if isinstance(usage, dict):
        input_tok = int(
            usage.get("input_tokens", usage.get("inputTokens", usage.get("prompt_tokens", 0)))
        )
        output_tok = int(
            usage.get("output_tokens", usage.get("outputTokens", usage.get("completion_tokens", 0)))
        )
        if input_tok or output_tok:
            return input_tok, output_tok

    # Flat keys
    input_tok = int(
        line_data.get("input_tokens",
        line_data.get("inputTokens",
        line_data.get("prompt_tokens", 0)))
    )
    output_tok = int(
        line_data.get("output_tokens",
        line_data.get("outputTokens",
        line_data.get("completion_tokens", 0)))
    )
    return input_tok, output_tok


def _extract_model(line_data: dict) -> str | None:
    """Extract model name from a log entry dict."""
    for key in ("model", "modelId", "model_id", "modelName"):
        val = line_data.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return None


def parse_log_for_provider(
    provider_name: str,
    model_prefix: str,
    start_date: str,
    end_date: str,
) -> List[UsageRecord]:
    """Parse the OpenClaw log file and return usage records for models matching model_prefix.

    Args:
        provider_name: Provider name string (e.g. "google", "moonshot")
        model_prefix:  Model name prefix to filter (e.g. "gemini-", "kimi-", "moonshot-")
        start_date:    ISO date YYYY-MM-DD (inclusive)
        end_date:      ISO date YYYY-MM-DD (inclusive)

    Returns:
        List of UsageRecord objects aggregated by (model, date).
    """
    log_path = _get_log_path()
    if not log_path.exists():
        logger.warning("Log parser: log file not found at %s", log_path)
        return []

    # Aggregate: key = (model, date), value = [input_tokens, output_tokens, request_count]
    agg: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0, 0])

    lines_parsed = 0
    lines_matched = 0

    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            lines_parsed += 1

            model = _extract_model(data)
            if not model:
                continue
            if not model.lower().startswith(model_prefix.lower()):
                continue

            entry_date = _extract_date(data)
            if not entry_date:
                continue
            if not (start_date <= entry_date <= end_date):
                continue

            input_tok, output_tok = _extract_tokens(data)
            if input_tok == 0 and output_tok == 0:
                continue  # Skip entries with no token info

            key = (model, entry_date)
            agg[key][0] += input_tok
            agg[key][1] += output_tok
            agg[key][2] += 1
            lines_matched += 1

    logger.info(
        "Log parser [%s]: parsed %d lines, matched %d token entries, %d unique (model, date) pairs",
        provider_name, lines_parsed, lines_matched, len(agg),
    )

    records: List[UsageRecord] = []
    for (model, date_str), (inp, out, req_count) in agg.items():
        records.append(UsageRecord(
            provider=provider_name,
            model=model,
            date=date_str,
            input_tokens=inp,
            output_tokens=out,
            total_tokens=inp + out,
            request_count=req_count,
            estimated_cost_usd=0.0,  # No billing data available from logs
        ))

    return records
