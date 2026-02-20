"""
OpenClaw session parser — extracts token usage from session JSONL files.

Data source: ~/.openclaw/agents/main/sessions/*.jsonl
             Also reads archived sessions: *.jsonl.deleted.* and *.jsonl.reset.*

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

    Reads active sessions (*.jsonl) as well as archived sessions:
      - *.jsonl.deleted.TIMESTAMP  (sessions removed/reset by user)
      - *.jsonl.reset.TIMESTAMP    (sessions reset by user)

    Args:
        model_prefixes: Optional list of model id prefixes to filter by
                        (e.g. ["claude", "gemini", "kimi"]). None = all models.
        start_date: Optional ISO date string YYYY-MM-DD (inclusive).
        end_date:   Optional ISO date string YYYY-MM-DD (inclusive).

    Returns:
        List of dicts with keys: provider, model, date, hour, input_tokens,
        output_tokens, cache_read_tokens, cache_write_tokens, real_tokens,
        request_count, estimated_cost_usd.
    """
    sessions_path = _get_sessions_path()

    if not sessions_path.exists():
        logger.warning("Sessions path does not exist: %s", sessions_path)
        return []

    # Collect all session file variants (active + deleted + reset), skip lock files
    session_files = []
    for pattern in ["*.jsonl", "*.jsonl.deleted.*", "*.jsonl.reset.*"]:
        session_files.extend(sessions_path.glob(pattern))
    session_files = [f for f in session_files if not f.name.endswith(".lock")]

    if not session_files:
        logger.info("No session files found in %s", sessions_path)
        return []

    # Accumulator: (provider, model, date, hour) -> dict of aggregated values
    agg: Dict[AggKey, Dict] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
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
                    cache_write_t = usage.get("cacheWrite", 0)
                    real_t = input_t + output_t  # billable tokens only

                    key: AggKey = (provider, model, date, hour)
                    bucket = agg[key]
                    bucket["input_tokens"] += input_t
                    bucket["output_tokens"] += output_t
                    bucket["cache_read_tokens"] += cache_read_t
                    bucket["cache_write_tokens"] += cache_write_t
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
                "cache_write_tokens": bucket["cache_write_tokens"],
                "real_tokens": bucket["real_tokens"],
                "request_count": bucket["request_count"],
                "estimated_cost_usd": bucket["estimated_cost_usd"],
            }
        )

    return result


def parse_single_session(file_path: Path) -> Dict:
    """
    Parse a single session JSONL file and return per-model token totals.

    Returns a dict keyed by model name, each value containing aggregated token
    counts and the session start time (earliest timestamp in the file).

    Return format:
        {
            "started_at": "2026-02-18T11:00:00+00:00",
            "message_count": 42,
            "by_model": {
                "claude-sonnet-4-6": {
                    "provider": "anthropic",
                    "input_tokens": 1200,
                    "output_tokens": 55000,
                    "cache_read_tokens": 8200000,
                    "cache_write_tokens": 1900000,
                    "request_count": 42,
                }
            }
        }
    """
    result: Dict[str, Dict] = {}
    started_at: str | None = None
    message_count = 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Track earliest timestamp as session start
                ts = record.get("timestamp", "")
                if ts and (started_at is None or ts < started_at):
                    started_at = ts

                if record.get("type") != "message":
                    continue
                msg = record.get("message", {})
                if msg.get("role") != "assistant":
                    continue

                message_count += 1

                usage = msg.get("usage")
                if not usage:
                    continue

                provider = msg.get("provider", "unknown")
                model = msg.get("model", "unknown")

                if model not in result:
                    result[model] = {
                        "provider": provider,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "request_count": 0,
                    }

                bucket = result[model]
                bucket["input_tokens"]       += usage.get("input", 0)
                bucket["output_tokens"]      += usage.get("output", 0)
                bucket["cache_read_tokens"]  += usage.get("cacheRead", 0)
                bucket["cache_write_tokens"] += usage.get("cacheWrite", 0)
                bucket["request_count"]      += 1

    except Exception as exc:
        logger.warning("Failed to parse session file %s: %s", file_path, exc)

    return {
        "started_at": started_at,
        "message_count": message_count,
        "by_model": result,
    }


# Tool name mapping for aggregation
TOOL_MAPPING = {
    "web_search": "brave",
    "web_fetch": "brave",
    "browser": "browser",
    "exec": "system",
    "read": "system",
    "write": "system",
    "edit": "system",
    "image": "image",
    "sessions_spawn": "orchestration",
    "sessions_send": "orchestration",
    "subagents": "orchestration",
    "memory_search": "memory",
    "memory_get": "memory",
}


def parse_tool_calls(
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict]:
    """
    Parse all session JSONL files and return aggregated tool call records.

    Tool calls are identified by messages with type "toolCall".
    We aggregate by (provider, tool_name, date, hour).

    Args:
        start_date: Optional ISO date string YYYY-MM-DD (inclusive).
        end_date:   Optional ISO date string YYYY-MM-DD (inclusive).

    Returns:
        List of dicts with keys: provider, tool_name, date, hour, call_count.
    """
    sessions_path = _get_sessions_path()

    if not sessions_path.exists():
        logger.warning("Sessions path does not exist: %s", sessions_path)
        return []

    # Collect all session file variants
    session_files = []
    for pattern in ["*.jsonl", "*.jsonl.deleted.*", "*.jsonl.reset.*"]:
        session_files.extend(sessions_path.glob(pattern))
    session_files = [f for f in session_files if not f.name.endswith(".lock")]

    if not session_files:
        logger.info("No session files found in %s", sessions_path)
        return []

    # Accumulator: (provider, tool_name, date, hour) -> count
    ToolKey = Tuple[str, str, str, int]
    agg: Dict[ToolKey, int] = defaultdict(int)

    files_parsed = 0
    calls_found = 0

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

                    # Look for toolCall messages
                    if record.get("type") != "message":
                        continue
                    msg = record.get("message", {})
                    content = msg.get("content", [])
                    if not isinstance(content, list):
                        continue

                    # Find toolCall items in content
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") != "toolCall":
                            continue

                        tool_name = item.get("name", "unknown")
                        timestamp = record.get("timestamp", "")
                        date, hour = _parse_date_hour(timestamp)

                        # Filter by date range
                        if start_date and date < start_date:
                            continue
                        if end_date and date > end_date:
                            continue

                        # Map tool to provider category
                        provider = TOOL_MAPPING.get(tool_name, "other")

                        key: ToolKey = (provider, tool_name, date, hour)
                        agg[key] += 1
                        calls_found += 1

            files_parsed += 1
        except Exception as exc:
            logger.warning("Failed to parse session file %s: %s", session_file, exc)

    logger.info(
        "Parsed %d session files, found %d tool calls across %d buckets",
        files_parsed,
        calls_found,
        len(agg),
    )

    result = []
    for (provider, tool_name, date, hour), count in sorted(agg.items()):
        result.append(
            {
                "provider": provider,
                "tool_name": tool_name,
                "date": date,
                "hour": hour,
                "call_count": count,
            }
        )

    return result
