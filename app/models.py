"""
Pydantic response models for API endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel


class PeriodStats(BaseModel):
    real_tokens: int
    requests: int


class UsageSummary(BaseModel):
    total_real_tokens: int
    total_cache_tokens: int
    total_requests: int
    estimated_cost_usd: float
    by_period: dict  # keys: today, last_7d, last_30d → PeriodStats-like dicts


class UsageByModel(BaseModel):
    provider: str
    model: str
    real_tokens: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    request_count: int
    estimated_cost_usd: float


class DailyUsage(BaseModel):
    date: str
    real_tokens: int
    requests: int


class HourlyUsage(BaseModel):
    hour: int
    real_tokens: int
    requests: int


class WeeklyUsage(BaseModel):
    week_start: str
    week_end: str
    days: List[DailyUsage]


class HourlyBreakdown(BaseModel):
    date: str
    hours: List[HourlyUsage]


class ProviderStatus(BaseModel):
    name: str
    display_name: str
    is_configured: bool
    method: str


class SyncLogEntry(BaseModel):
    id: int
    provider: str
    status: str
    message: Optional[str]
    synced_at: str


class SyncResult(BaseModel):
    triggered: bool
    providers_synced: List[str]
    message: str
