"""
OpenClaw session parser — extracts token usage from session JSONL files.

Data source: ~/.openclaw/agents/main/sessions/*.jsonl

Each session file contains one JSON object per line. Assistant messages
include a `usage` field with per-call token counts and cost. This module
reads all session files, extracts usage from assistant messages, and
aggregates by (provider, model, date, hour).

Record format (assistant message with usage):
{
    "type": "message",
    "timestamp": "2026-02-18T08:00:00.000Z",
    "message": {
        "role": "assistant",
        "provider": "moonshot",
        "model": "kimi-k2.5",
        "usage": {
            "input": 2893,
            "output": 100,
            "cacheRead": 6144,
            "cacheWrite": 0,
            "totalTokens": 9137,
            "cost": {
                "input": 0.0,
                "output": 0.0,
                "cacheRead": 0.0,
                "cacheWrite": 0.0
            }
        }
    }
}

Session directory is read from OPENCLAW_SESSIONS_PATH env var, defaulting
to ~/.openclaw/agents/main/sessions.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_PATH = "~/.openclaw/agents/main/sessions"


def _get_sessions_path() -> Path:
    raw = os.getenv("OPENCLAW_SESSIONS_PATH", DEFAULT_SESSIONS_PATH)
    return Path(raw).expanduser().resolve()


def _parse_date_hour(timestamp_str: str) -> Tuple[str, int]:
    """Parse ISO timestamp string to (YYYY-MM-DD, hour) tuple in UTC."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%d"), dt_utc.hour
    except Exception:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d"), now.hour


# Key: (provider, model, date, hour)
AggKey = Tuple[str, str, str, int]


def parse_sessions(
    model_prefixes: List[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict]:
    """
    Parse all session JSONL files and return aggregated usage records.

    Args:
        model_prefixes: Optional list of model id prefixes to filter by
                        (e.g. ["claude", "gemini", "kimi"]). None = all models.
        start_date: Optional ISO date string YYYY-MM-DD (inclusive).
        end_date:   Optional ISO date string YYYY-MM-DD (inclusive).

    Returns:
        List of dicts with keys: provider, model, date, hour, input_tokens,
        output_tokens, cache_read_tokens, real_tokens, request_count,
        estimated_cost_usd.
    """
    sessions_path = _get_sessions_path()

    if not sessions_path.exists():
        logger.warning("Sessions path does not exist: %s", sessions_path)
        return []

    session_files = list(sessions_path.glob("*.jsonl"))
    if not session_files:
        logger.info("No session files found in %s", sessions_path)
        return []

    # Accumulator: (provider, model, date, hour) -> dict of aggregated values
    agg: Dict[AggKey, Dict] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "real_tokens": 0,
            "request_count": 0,
            "estimated_cost_usd": 0.0,
        }
    )

    files_parsed = 0
    records_found = 0

    for session_file in session_files:
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Only process assistant messages with usage data
                    if record.get("type") != "message":
                        continue
                    msg = record.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    usage = msg.get("usage")
                    if not usage:
                        continue

                    provider = msg.get("provider", "unknown")
                    model = msg.get("model", "unknown")
                    timestamp = record.get("timestamp", "")
                    date, hour = _parse_date_hour(timestamp)

                    # Filter by model prefix
                    if model_prefixes:
                        if not any(model.startswith(p) for p in model_prefixes):
                            continue

                    # Filter by date range
                    if start_date and date < start_date:
                        continue
                    if end_date and date > end_date:
                        continue

                    # Extract cost — sum across all cost fields
                    cost_obj = usage.get("cost", {})
                    cost = sum(
                        v for v in cost_obj.values() if isinstance(v, (int, float))
                    )

                    input_t = usage.get("input", 0)
                    output_t = usage.get("output", 0)
                    cache_read_t = usage.get("cacheRead", 0)
                    real_t = input_t + output_t  # billable tokens only

                    key: AggKey = (provider, model, date, hour)
                    bucket = agg[key]
                    bucket["input_tokens"] += input_t
                    bucket["output_tokens"] += output_t
                    bucket["cache_read_tokens"] += cache_read_t
                    bucket["real_tokens"] += real_t
                    bucket["request_count"] += 1
                    bucket["estimated_cost_usd"] += cost
                    records_found += 1

            files_parsed += 1
        except Exception as exc:
            logger.warning("Failed to parse session file %s: %s", session_file, exc)

    logger.info(
        "Parsed %d session files, found %d usage records across %d (provider, model, date, hour) buckets",
        files_parsed,
        records_found,
        len(agg),
    )

    result = []
    for (provider, model, date, hour), bucket in sorted(agg.items()):
        result.append(
            {
                "provider": provider,
                "model": model,
                "date": date,
                "hour": hour,
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "cache_read_tokens": bucket["cache_read_tokens"],
                "real_tokens": bucket["real_tokens"],
                "request_count": bucket["request_count"],
                "estimated_cost_usd": bucket["estimated_cost_usd"],
            }
        )

    return result
