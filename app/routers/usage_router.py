"""
Usage API endpoints.

GET /api/usage/summary    — aggregate totals (all time, 30d, 7d)
GET /api/usage/by-model   — breakdown per model, sorted by total_tokens desc
GET /api/usage/timeline   — daily totals for last 30 days
GET /api/usage/by-provider — aggregated per provider
"""

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, HTTPException

from ..database import get_db
from ..models import UsageSummary, UsageByModel, DailyUsage, UsageByProvider
from ..providers import ALL_PROVIDERS

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _date_n_days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


@router.get("/summary", response_model=UsageSummary)
async def get_summary():
    """Return aggregate token totals and cost across all providers."""
    date_30d = _date_n_days_ago(30)
    date_7d = _date_n_days_ago(7)

    async with await get_db() as db:
        # All-time totals
        row = await (await db.execute(
            "SELECT SUM(total_tokens) as tt, SUM(request_count) as rc FROM usage_records"
        )).fetchone()
        total_tokens_all = int(row["tt"] or 0)
        total_requests = int(row["rc"] or 0)

        # Last 30 days
        row = await (await db.execute(
            "SELECT SUM(total_tokens) as tt, SUM(estimated_cost_usd) as cost "
            "FROM usage_records WHERE date >= ?", (date_30d,)
        )).fetchone()
        total_tokens_30d = int(row["tt"] or 0)
        cost_30d = float(row["cost"] or 0.0)

        # Last 7 days
        row = await (await db.execute(
            "SELECT SUM(total_tokens) as tt FROM usage_records WHERE date >= ?", (date_7d,)
        )).fetchone()
        total_tokens_7d = int(row["tt"] or 0)

    active_providers = sum(1 for p in ALL_PROVIDERS if p.is_configured())

    return UsageSummary(
        total_tokens_all_time=total_tokens_all,
        total_tokens_last_30d=total_tokens_30d,
        total_tokens_last_7d=total_tokens_7d,
        estimated_cost_last_30d=cost_30d,
        active_providers=active_providers,
        total_requests_all_time=total_requests,
    )


@router.get("/by-model", response_model=List[UsageByModel])
async def get_by_model():
    """Return per-model breakdown sorted by total token volume (descending)."""
    async with await get_db() as db:
        rows = await (await db.execute("""
            SELECT
                provider,
                model,
                SUM(total_tokens)        AS total_tokens,
                SUM(input_tokens)        AS input_tokens,
                SUM(output_tokens)       AS output_tokens,
                SUM(request_count)       AS request_count,
                SUM(estimated_cost_usd)  AS estimated_cost_usd
            FROM usage_records
            GROUP BY provider, model
            ORDER BY total_tokens DESC
        """)).fetchall()

    return [
        UsageByModel(
            provider=r["provider"],
            model=r["model"],
            total_tokens=int(r["total_tokens"] or 0),
            input_tokens=int(r["input_tokens"] or 0),
            output_tokens=int(r["output_tokens"] or 0),
            request_count=int(r["request_count"] or 0),
            estimated_cost_usd=float(r["estimated_cost_usd"] or 0.0),
        )
        for r in rows
    ]


@router.get("/timeline", response_model=List[DailyUsage])
async def get_timeline():
    """Return daily aggregate totals for the last 30 days."""
    date_30d = _date_n_days_ago(30)

    async with await get_db() as db:
        rows = await (await db.execute("""
            SELECT
                date,
                SUM(total_tokens)   AS total_tokens,
                SUM(input_tokens)   AS input_tokens,
                SUM(output_tokens)  AS output_tokens,
                SUM(request_count)  AS request_count
            FROM usage_records
            WHERE date >= ?
            GROUP BY date
            ORDER BY date ASC
        """, (date_30d,))).fetchall()

    return [
        DailyUsage(
            date=r["date"],
            total_tokens=int(r["total_tokens"] or 0),
            input_tokens=int(r["input_tokens"] or 0),
            output_tokens=int(r["output_tokens"] or 0),
            request_count=int(r["request_count"] or 0),
        )
        for r in rows
    ]


@router.get("/by-provider", response_model=List[UsageByProvider])
async def get_by_provider():
    """Return totals aggregated per provider."""
    provider_map = {p.name: p.display_name for p in ALL_PROVIDERS}

    async with await get_db() as db:
        rows = await (await db.execute("""
            SELECT
                provider,
                SUM(total_tokens)        AS total_tokens,
                SUM(input_tokens)        AS input_tokens,
                SUM(output_tokens)       AS output_tokens,
                SUM(request_count)       AS request_count,
                SUM(estimated_cost_usd)  AS estimated_cost_usd
            FROM usage_records
            GROUP BY provider
            ORDER BY total_tokens DESC
        """)).fetchall()

    return [
        UsageByProvider(
            provider=r["provider"],
            display_name=provider_map.get(r["provider"], r["provider"]),
            total_tokens=int(r["total_tokens"] or 0),
            input_tokens=int(r["input_tokens"] or 0),
            output_tokens=int(r["output_tokens"] or 0),
            request_count=int(r["request_count"] or 0),
            estimated_cost_usd=float(r["estimated_cost_usd"] or 0.0),
        )
        for r in rows
    ]
