"""
Base provider interface for OpenClaw Usage Dashboard.

All provider implementations must inherit from BaseProvider and implement:
  - fetch_usage(start_date, end_date): returns List[UsageRecord]
  - is_configured(): returns True if required env vars are present

Registration: add provider instances to ALL_PROVIDERS in app/providers/__init__.py
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class UsageRecord:
    """Normalised usage record returned by all providers."""
    provider: str
    model: str
    date: str               # ISO date YYYY-MM-DD
    input_tokens: int
    output_tokens: int
    total_tokens: int
    request_count: int
    estimated_cost_usd: float


class BaseProvider(ABC):
    name: str           # e.g. "anthropic"     — used as DB key
    display_name: str   # e.g. "Anthropic"     — shown in UI

    @abstractmethod
    async def fetch_usage(self, start_date: str, end_date: str) -> List[UsageRecord]:
        """Fetch usage records from provider for the given date range.

        Args:
            start_date: ISO date string YYYY-MM-DD (inclusive)
            end_date:   ISO date string YYYY-MM-DD (inclusive)

        Returns:
            List of UsageRecord objects, one per (model, date) combination.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if all required environment variables are set."""
        pass
