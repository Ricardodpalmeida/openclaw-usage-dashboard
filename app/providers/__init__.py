"""
Provider registry — the single registration point for all providers.

To add a new provider:
  1. Create app/providers/{name}_provider.py implementing BaseProvider
  2. Import and add an instance to ALL_PROVIDERS below
  3. Add required env var(s) to .env.example and docker-compose.yml
"""

from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleProvider
from .moonshot_provider import MoonshotProvider

ALL_PROVIDERS = [
    AnthropicProvider(),
    GoogleProvider(),
    MoonshotProvider(),
]

__all__ = ["ALL_PROVIDERS"]
