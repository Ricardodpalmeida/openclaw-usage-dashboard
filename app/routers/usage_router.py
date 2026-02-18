"""
Usage API endpoints.

GET /api/usage/summary           — aggregate totals (last 30d) with period breakdown
GET /api/usage/weekly            — daily totals for a given week (Mon–Sun)
GET /api/usage/hourly            — per-hour breakdown for a given date
GET /api/usage/by-model          — breakdown per model, sorted by real_tokens desc
"""

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import (
    UsageSummary, UsageByModel, WeeklyUsage, HourlyBreakdown,
    DailyUsage, HourlyUsage,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])


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


@router.get("/weekly")
async def get_weekly(week_offset: int = Query(default=0)):
    """Return daily real_tokens + request totals for the 7 days of the requested week."""
    week_start, week_end = _week_bounds(week_offset)

    async with get_db() as db:
        rows = await (await db.execute("""
            SELECT date,
                   SUM(real_tokens)   AS rt,
                   SUM(request_count) AS rc
            FROM usage_records
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date ASC
        """, (week_start, week_end))).fetchall()

    # Build a map for the 7 days (fill zeros for missing days)
    row_map = {r["date"]: (int(r["rt"] or 0), int(r["rc"] or 0)) for r in rows}

    days = []
    start = date.fromisoformat(week_start)
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        rt, rc = row_map.get(d, (0, 0))
        days.append({"date": d, "real_tokens": rt, "requests": rc})

    return {
        "week_start": week_start,
        "week_end": week_end,
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
                SUM(real_tokens)         AS real_tokens,
                SUM(input_tokens)        AS input_tokens,
                SUM(output_tokens)       AS output_tokens,
                SUM(cache_read_tokens)   AS cache_read_tokens,
                SUM(request_count)       AS request_count,
                SUM(estimated_cost_usd)  AS estimated_cost_usd
            FROM usage_records
            WHERE date >= ?
            GROUP BY provider, model
            ORDER BY real_tokens DESC
        """, (date_30d,))).fetchall()

    return [
        UsageByModel(
            provider=r["provider"],
            model=r["model"],
            real_tokens=int(r["real_tokens"] or 0),
            input_tokens=int(r["input_tokens"] or 0),
            output_tokens=int(r["output_tokens"] or 0),
            cache_read_tokens=int(r["cache_read_tokens"] or 0),
            request_count=int(r["request_count"] or 0),
            estimated_cost_usd=float(r["estimated_cost_usd"] or 0.0),
        )
        for r in rows
    ]
