"""
Pydantic response models for API endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_tokens_all_time: int
    total_tokens_last_30d: int
    total_tokens_last_7d: int
    estimated_cost_last_30d: float
    active_providers: int
    total_requests_all_time: int


class UsageByModel(BaseModel):
    provider: str
    model: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    request_count: int
    estimated_cost_usd: float


class DailyUsage(BaseModel):
    date: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    request_count: int


class UsageByProvider(BaseModel):
    provider: str
    display_name: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    request_count: int
    estimated_cost_usd: float


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
