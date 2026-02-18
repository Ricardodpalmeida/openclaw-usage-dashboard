"""
Usage API endpoints.

GET /api/usage/summary           — aggregate totals (last 30d) with period breakdown
GET /api/usage/weekly            — daily totals for a given week (Mon–Sun)
GET /api/usage/weekly-by-model   — daily totals per model for a given week
GET /api/usage/hourly            — per-hour breakdown for a given date
GET /api/usage/by-model          — breakdown per model, sorted by real_tokens desc
GET /api/session/current         — live stats for the currently active session
"""

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Query

from ..database import get_db, get_all_pricing, get_setting
from ..log_parser import parse_single_session
from ..models import (
    UsageSummary, UsageByModel, WeeklyUsage, HourlyBreakdown,
    DailyUsage, HourlyUsage,
)
from ..pricing import estimate_cost

router = APIRouter(prefix="/api/usage", tags=["usage"])
session_router = APIRouter(prefix="/api/session", tags=["session"])

_DEFAULT_SESSIONS_PATH = "~/.openclaw/agents/main/sessions"


def _sessions_path() -> Path:
    raw = os.getenv("OPENCLAW_SESSIONS_PATH", _DEFAULT_SESSIONS_PATH)
    return Path(raw).expanduser().resolve()


def _find_active_session() -> Path | None:
    """Return the active session JSONL path, identified by a corresponding .lock file."""
    sp = _sessions_path()
    if not sp.exists():
        return None
    for lock in sp.glob("*.jsonl.lock"):
        candidate = sp / lock.name.removesuffix(".lock")
        if candidate.exists():
            return candidate
    return None


async def get_current_session_data(db) -> dict:
    """
    Compute live cost and token stats for the currently active session.
    Accepts an open DB connection — used by both the API endpoint and the alerting module.
    """
    active = _find_active_session()
    if active is None:
        return {"status": "no_active_session"}

    session_id = active.stem  # UUID part of filename
    parsed = parse_single_session(active)

    pricing_rows = await get_all_pricing(db)
    threshold_str = await get_setting(db, "session_cost_warning_usd", "5.0")

    threshold = float(threshold_str)
    pricing_map = {r["model"]: dict(r) for r in pricing_rows}

    # Aggregate across models
    total_input = total_output = total_cache_read = total_cache_write = 0
    total_cost = 0.0
    models_used = []

    for model, bucket in parsed["by_model"].items():
        models_used.append(model)
        total_input       += bucket["input_tokens"]
        total_output      += bucket["output_tokens"]
        total_cache_read  += bucket["cache_read_tokens"]
        total_cache_write += bucket["cache_write_tokens"]
        pr = pricing_map.get(model)
        if pr:
            total_cost += estimate_cost(
                model, pr,
                bucket["input_tokens"],
                bucket["output_tokens"],
                bucket["cache_read_tokens"],
                bucket["cache_write_tokens"],
            )

    # Duration
    started_at = parsed.get("started_at")
    duration_minutes = 0
    if started_at:
        try:
            dt_start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            duration_minutes = int(
                (datetime.now(timezone.utc) - dt_start).total_seconds() / 60
            )
        except Exception:
            pass

    return {
        "status": "ok",
        "session_id": session_id,
        "message_count": parsed["message_count"],
        "models_used": models_used,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read_tokens": total_cache_read,
        "cache_write_tokens": total_cache_write,
        "estimated_cost_usd": round(total_cost, 4),
        "started_at": started_at,
        "duration_minutes": duration_minutes,
        "warning": total_cost >= threshold,
        "warning_threshold_usd": threshold,
    }


@session_router.get("/current")
async def get_current_session():
    """Return live cost and token stats for the currently active session."""
    async with get_db() as db:
        return await get_current_session_data(db)


def _date_n_days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _week_bounds(week_offset: int = 0):
    """Return (week_start, week_end) ISO strings for Mon–Sun of the requested week."""
    today = date.today()
    # Monday of current week
    monday = today - timedelta(days=today.weekday())
    # Shift by week_offset (negative = past weeks)
    week_start = monday + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


@router.get("/summary")
async def get_summary():
    """Return aggregate token totals and cost, broken down by period."""
    today = date.today().isoformat()
    date_7d = _date_n_days_ago(7)
    date_30d = _date_n_days_ago(30)

    async with get_db() as db:
        # Last 30 days totals
        row = await (await db.execute(
            "SELECT SUM(real_tokens) as rt, SUM(cache_read_tokens) as cr, "
            "SUM(request_count) as rc, SUM(estimated_cost_usd) as cost "
            "FROM usage_records WHERE date >= ?", (date_30d,)
        )).fetchone()
        total_real = int(row["rt"] or 0)
        total_cache = int(row["cr"] or 0)
        total_requests = int(row["rc"] or 0)
        total_cost = float(row["cost"] or 0.0)

        # Today
        row_today = await (await db.execute(
            "SELECT SUM(real_tokens) as rt, SUM(request_count) as rc "
            "FROM usage_records WHERE date = ?", (today,)
        )).fetchone()

        # Last 7 days
        row_7d = await (await db.execute(
            "SELECT SUM(real_tokens) as rt, SUM(request_count) as rc "
            "FROM usage_records WHERE date >= ?", (date_7d,)
        )).fetchone()

    return {
        "total_real_tokens": total_real,
        "total_cache_tokens": total_cache,
        "total_requests": total_requests,
        "estimated_cost_usd": total_cost,
        "by_period": {
            "today": {
                "real_tokens": int(row_today["rt"] or 0),
                "requests": int(row_today["rc"] or 0),
            },
            "last_7d": {
                "real_tokens": int(row_7d["rt"] or 0),
                "requests": int(row_7d["rc"] or 0),
            },
            "last_30d": {
                "real_tokens": total_real,
                "requests": total_requests,
            },
        },
    }


_VALID_TOKEN_TYPES = {"input", "output", "cache_read", "cache_write"}
_TOKEN_TYPE_COLUMN = {
    "input":       "input_tokens",
    "output":      "output_tokens",
    "cache_read":  "cache_read_tokens",
    "cache_write": "cache_write_tokens",
}


@router.get("/weekly")
async def get_weekly(
    week_offset: int = Query(default=0),
    token_type: str = Query(default="output"),
):
    """Return daily token totals for the 7 days of the requested week.

    token_type: one of input | output | cache_read | cache_write (default: output)
    """
    if token_type not in _VALID_TOKEN_TYPES:
        token_type = "output"
    col = _TOKEN_TYPE_COLUMN[token_type]
    week_start, week_end = _week_bounds(week_offset)

    async with get_db() as db:
        rows = await (await db.execute(f"""
            SELECT date,
                   SUM({col})         AS tokens,
                   SUM(request_count) AS rc
            FROM usage_records
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date ASC
        """, (week_start, week_end))).fetchall()

    # Build a map for the 7 days (fill zeros for missing days)
    row_map = {r["date"]: (int(r["tokens"] or 0), int(r["rc"] or 0)) for r in rows}

    days = []
    start = date.fromisoformat(week_start)
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        tokens, rc = row_map.get(d, (0, 0))
        days.append({"date": d, "tokens": tokens, "token_type": token_type, "requests": rc})

    return {
        "week_start": week_start,
        "week_end": week_end,
        "token_type": token_type,
        "days": days,
    }


@router.get("/hourly")
async def get_hourly(date_param: str = Query(alias="date", default=None)):
    """Return per-hour real_tokens + request breakdown for a given date."""
    if date_param is None:
        date_param = date.today().isoformat()

    async with get_db() as db:
        rows = await (await db.execute("""
            SELECT hour,
                   SUM(real_tokens)   AS rt,
                   SUM(request_count) AS rc
            FROM usage_records
            WHERE date = ?
            GROUP BY hour
            ORDER BY hour ASC
        """, (date_param,))).fetchall()

    row_map = {r["hour"]: (int(r["rt"] or 0), int(r["rc"] or 0)) for r in rows}

    hours = []
    for h in range(24):
        rt, rc = row_map.get(h, (0, 0))
        hours.append({"hour": h, "real_tokens": rt, "requests": rc})

    return {"date": date_param, "hours": hours}


@router.get("/by-model", response_model=List[UsageByModel])
async def get_by_model():
    """Return per-model breakdown for the last 30 days, sorted by real_tokens desc."""
    date_30d = _date_n_days_ago(30)

    async with get_db() as db:
        rows = await (await db.execute("""
            SELECT
                provider,
                model,
                SUM(real_tokens)          AS real_tokens,
                SUM(input_tokens)         AS input_tokens,
                SUM(output_tokens)        AS output_tokens,
                SUM(cache_read_tokens)    AS cache_read_tokens,
                SUM(cache_write_tokens)   AS cache_write_tokens,
                SUM(request_count)        AS request_count,
                SUM(estimated_cost_usd)   AS estimated_cost_usd
            FROM usage_records
            WHERE date >= ?
            GROUP BY provider, model
            ORDER BY output_tokens DESC
        """, (date_30d,))).fetchall()

    return [
        UsageByModel(
            provider=r["provider"],
            model=r["model"],
            real_tokens=int(r["real_tokens"] or 0),
            input_tokens=int(r["input_tokens"] or 0),
            output_tokens=int(r["output_tokens"] or 0),
            cache_read_tokens=int(r["cache_read_tokens"] or 0),
            cache_write_tokens=int(r["cache_write_tokens"] or 0),
            request_count=int(r["request_count"] or 0),
            estimated_cost_usd=float(r["estimated_cost_usd"] or 0.0),
        )
        for r in rows
    ]


@router.get("/weekly-by-model")
async def get_weekly_by_model(
    week_offset: int = Query(default=0),
    token_type: str = Query(default="output"),
):
    """Return daily token counts per model for the 7 days of the requested week.

    token_type: one of input | output | cache_read | cache_write (default: output)

    - models: all models with any usage in the last 30 days (for consistent color assignment)
    - days: each day has by_model dict zero-filled for all models
    """
    if token_type not in _VALID_TOKEN_TYPES:
        token_type = "output"
    col = _TOKEN_TYPE_COLUMN[token_type]

    week_start, week_end = _week_bounds(week_offset)
    date_30d = _date_n_days_ago(30)

    async with get_db() as db:
        # All models with usage in last 30 days, ordered by total output tokens desc
        model_rows = await (await db.execute("""
            SELECT model, SUM(output_tokens) AS total_out
            FROM usage_records
            WHERE date >= ?
            GROUP BY model
            ORDER BY total_out DESC
        """, (date_30d,))).fetchall()

        # Per-day per-model data for the requested week (selected token type)
        week_rows = await (await db.execute(f"""
            SELECT date, model, SUM({col}) AS tokens
            FROM usage_records
            WHERE date >= ? AND date <= ?
            GROUP BY date, model
            ORDER BY date ASC
        """, (week_start, week_end))).fetchall()

    models = [r["model"] for r in model_rows]

    # Build lookup: {date: {model: tokens}}
    week_map: dict = {}
    for r in week_rows:
        d = r["date"]
        if d not in week_map:
            week_map[d] = {}
        week_map[d][r["model"]] = int(r["tokens"] or 0)

    # Build 7-day response
    start = date.fromisoformat(week_start)
    days = []
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        day_label = (start + timedelta(days=i)).strftime("%a %-d")
        by_model = {m: week_map.get(d, {}).get(m, 0) for m in models}
        days.append({"date": d, "label": day_label, "by_model": by_model})

    return {
        "week_start": week_start,
        "week_end": week_end,
        "token_type": token_type,
        "models": models,
        "days": days,
    }


# (Pricing endpoints moved to routers/pricing_router.py)
