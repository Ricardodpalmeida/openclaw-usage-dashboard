"""
Database layer — SQLite via aiosqlite.

Database file is stored at /app/data/usage.db inside the container, or
./data/usage.db locally (matched by the Docker volume mount).

Schema is applied on startup via init_db(); no migration framework needed
at this scale — schema changes require a manual DB reset or ALTER TABLE.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/usage.db"))


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager for a database connection. Use as: async with get_db() as db."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS usage_records (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                provider            TEXT NOT NULL,
                model               TEXT NOT NULL,
                date                TEXT NOT NULL,           -- ISO date YYYY-MM-DD
                input_tokens        INTEGER DEFAULT 0,
                output_tokens       INTEGER DEFAULT 0,
                total_tokens        INTEGER DEFAULT 0,
                request_count       INTEGER DEFAULT 0,
                estimated_cost_usd  REAL    DEFAULT 0.0,
                synced_at           TEXT NOT NULL,
                UNIQUE(provider, model, date)
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                provider    TEXT NOT NULL,
                status      TEXT NOT NULL,       -- 'ok' | 'error'
                message     TEXT,
                synced_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_usage_date
                ON usage_records(date);

            CREATE INDEX IF NOT EXISTS idx_usage_provider
                ON usage_records(provider);
        """)
        await db.commit()

    logger.info("Database ready at %s", DB_PATH)


async def upsert_usage_record(db: aiosqlite.Connection, record: dict) -> None:
    """Insert or update a usage record (conflict on provider+model+date adds tokens)."""
    await db.execute("""
        INSERT INTO usage_records
            (provider, model, date, input_tokens, output_tokens, total_tokens,
             request_count, estimated_cost_usd, synced_at)
        VALUES
            (:provider, :model, :date, :input_tokens, :output_tokens, :total_tokens,
             :request_count, :estimated_cost_usd, :synced_at)
        ON CONFLICT(provider, model, date) DO UPDATE SET
            input_tokens        = excluded.input_tokens,
            output_tokens       = excluded.output_tokens,
            total_tokens        = excluded.total_tokens,
            request_count       = excluded.request_count,
            estimated_cost_usd  = excluded.estimated_cost_usd,
            synced_at           = excluded.synced_at
    """, record)


async def insert_sync_log(db: aiosqlite.Connection, provider: str, status: str, message: str, synced_at: str) -> None:
    """Append a sync event to the sync_log table."""
    await db.execute(
        "INSERT INTO sync_log (provider, status, message, synced_at) VALUES (?, ?, ?, ?)",
        (provider, status, message, synced_at),
    )
