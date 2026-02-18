"""
Thin cost-estimation helper.

Pricing data is stored in the model_pricing DB table (see database.py).
Callers must fetch the pricing row from the DB and pass it here.
"""


def estimate_cost(
    model: str,
    pricing_row: dict,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
) -> float:
    """Return estimated cost in USD given a pricing row from the DB and token counts.

    pricing_row must have keys: input_per_m, output_per_m, cache_read_per_m, cache_write_per_m.
    Returns 0.0 if pricing_row is empty or None.
    """
    if not pricing_row:
        return 0.0
    return (
        input_tokens       / 1_000_000 * pricing_row.get("input_per_m", 0) +
        output_tokens      / 1_000_000 * pricing_row.get("output_per_m", 0) +
        cache_read_tokens  / 1_000_000 * pricing_row.get("cache_read_per_m", 0) +
        cache_write_tokens / 1_000_000 * pricing_row.get("cache_write_per_m", 0)
    )
