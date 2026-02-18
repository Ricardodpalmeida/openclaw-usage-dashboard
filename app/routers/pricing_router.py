"""
Pricing API endpoints.

GET    /api/pricing              — list all model pricing rows from DB
PUT    /api/pricing/{model}      — create or update a model's pricing
DELETE /api/pricing/{model}      — remove a model's pricing entry

After a PUT, all usage_records for the affected model have their
estimated_cost_usd recomputed using the new pricing.

Settings endpoints:
GET    /api/settings             — return all settings as {key: value}
POST   /api/settings             — update one or more settings keys
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_db, get_all_pricing, upsert_pricing, delete_pricing, get_all_settings, set_setting
from ..pricing import estimate_cost

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


class PricingUpdate(BaseModel):
    display_name: Optional[str] = None
    input_per_m: float = 0.0
    output_per_m: float = 0.0
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0


@router.get("")
async def list_pricing():
    """Return all model pricing rows from the DB, ordered by model name."""
    async with get_db() as db:
        rows = await get_all_pricing(db)
    return [dict(r) for r in rows]


@router.put("/{model:path}")
async def update_pricing(model: str, body: PricingUpdate):
    """Create or update pricing for a model, then recompute costs for all matching usage records."""
    display_name = body.display_name or model  # fall back to model ID if no display name given

    async with get_db() as db:
        await upsert_pricing(
            db,
            model=model,
            display_name=display_name,
            input_per_m=body.input_per_m,
            output_per_m=body.output_per_m,
            cache_read_per_m=body.cache_read_per_m,
            cache_write_per_m=body.cache_write_per_m,
        )

        # Recompute estimated_cost_usd for all usage_records with this model
        pricing_row = {
            "input_per_m":       body.input_per_m,
            "output_per_m":      body.output_per_m,
            "cache_read_per_m":  body.cache_read_per_m,
            "cache_write_per_m": body.cache_write_per_m,
        }
        records = await (await db.execute(
            """
            SELECT id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
            FROM usage_records WHERE model = ?
            """,
            (model,),
        )).fetchall()

        updated = 0
        for rec in records:
            cost = estimate_cost(
                model,
                pricing_row,
                rec["input_tokens"],
                rec["output_tokens"],
                rec["cache_read_tokens"],
                rec["cache_write_tokens"],
            )
            await db.execute(
                "UPDATE usage_records SET estimated_cost_usd = ? WHERE id = ?",
                (cost, rec["id"]),
            )
            updated += 1

        await db.commit()

    logger.info("Pricing updated for %s — recomputed cost for %d usage records", model, updated)
    return {
        "model": model,
        "display_name": display_name,
        "records_updated": updated,
    }


@router.delete("/{model:path}")
async def remove_pricing(model: str):
    """Delete the pricing entry for a model."""
    async with get_db() as db:
        n = await delete_pricing(db, model)
        await db.commit()

    if n == 0:
        raise HTTPException(status_code=404, detail=f"Model '{model}' not found in pricing table")

    return {"model": model, "deleted": True}


# ── Settings router ─────────────────────────────────────────────────────────

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


@settings_router.get("")
async def get_settings():
    """Return all application settings as a {key: value} dict."""
    async with get_db() as db:
        return await get_all_settings(db)


@settings_router.post("")
async def update_settings(body: Dict[str, Any]):
    """Update one or more settings keys. Accepts a JSON object of {key: value} pairs."""
    async with get_db() as db:
        for key, value in body.items():
            await set_setting(db, key, str(value))
        await db.commit()
    return {"updated": list(body.keys())}
