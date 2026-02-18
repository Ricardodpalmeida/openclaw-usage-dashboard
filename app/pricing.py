"""
Hard-coded API pricing per model (per million tokens).
Update these when provider pricing changes.
Source: official provider pricing pages, Feb 2026.
"""

PRICING = {
    # Anthropic
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00, "cache_read": 1.50,   "cache_write": 18.75},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00, "cache_read": 0.30,   "cache_write":  3.75},
    # Moonshot / Kimi
    "kimi-k2.5":         {"input":  0.60, "output":  3.00, "cache_read": 0.15,   "cache_write":  0.60},
    "kimi-k2-thinking":  {"input":  0.60, "output":  3.00, "cache_read": 0.15,   "cache_write":  0.60},
    # Google Gemini (for future use when tracked)
    "gemini-3-flash-preview": {"input": 0.10, "output": 0.40, "cache_read": 0.025, "cache_write": 0.10},
    "gemini-3-pro-preview":   {"input": 1.25, "output": 5.00, "cache_read": 0.3125,"cache_write": 1.25},
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
) -> float:
    """Return estimated cost in USD for a given model and token counts."""
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (
        input_tokens       / 1_000_000 * p["input"] +
        output_tokens      / 1_000_000 * p["output"] +
        cache_read_tokens  / 1_000_000 * p["cache_read"] +
        cache_write_tokens / 1_000_000 * p.get("cache_write", 0.0)
    )
