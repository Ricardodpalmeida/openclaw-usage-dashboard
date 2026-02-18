"""
Database layer — SQLite via aiosqlite.

Database file is stored at /app/data/usage.db inside the container, or
./data/usage.db locally (matched by the Docker volume mount).

Schema is applied on startup via init_db(). The usage_records table is
dropped and recreated on each startup to ensure schema consistency — data
is re-synced from session files on startup.

The model_pricing table persists across restarts and is seeded with defaults
only when empty (user edits are preserved).
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/usage.db"))

SEED_PRICING = [
    ("claude-opus-4-6",        "Claude Opus 4.6",   5.00, 25.00,  0.50,    6.25),
    ("claude-sonnet-4-6",      "Claude Sonnet 4.6",  3.00, 15.00,  0.30,    3.75),
    ("kimi-k2.5",              "Kimi K2.5",          0.60,  3.00,  0.15,    0.60),
    ("kimi-k2-thinking",       "Kimi K2 Thinking",   0.60,  3.00,  0.15,    0.60),
    ("gemini-3-flash-preview", "Gemini 3 Flash",     0.10,  0.40,  0.025,   0.10),
    ("gemini-3-pro-preview",   "Gemini 3 Pro",       1.25,  5.00,  0.3125,  1.25),
]


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager for a database connection. Use as: async with get_db() as db."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def seed_default_pricing(db: aiosqlite.Connection) -> None:
    """Insert default pricing rows only if the model_pricing table is empty."""
    row = await (await db.execute("SELECT COUNT(*) AS cnt FROM model_pricing")).fetchone()
    if row["cnt"] > 0:
        return  # User has already customised pricing — don't overwrite

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await db.executemany(
        """
        INSERT OR IGNORE INTO model_pricing
            (model, display_name, input_per_m, output_per_m, cache_read_per_m, cache_write_per_m, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(m, dn, inp, out, cr, cw, now) for m, dn, inp, out, cr, cw in SEED_PRICING],
    )


async def get_setting(db: aiosqlite.Connection, key: str, default: str = "") -> str:
    """Return the value for a settings key, or default if not found."""
    row = await (await db.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    )).fetchone()
    return row["value"] if row else default


async def set_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    """Insert or replace a settings key/value pair."""
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )


async def get_all_settings(db: aiosqlite.Connection) -> dict:
    """Return all settings as a {key: value} dict."""
    rows = await (await db.execute("SELECT key, value FROM settings")).fetchall()
    return {r["key"]: r["value"] for r in rows}


async def seed_default_settings(db: aiosqlite.Connection) -> None:
    """Seed default settings if they don't already exist."""
    defaults = [
        ("session_cost_warning_usd", "5.0"),
        ("alert_whatsapp_enabled", "false"),
        ("alert_whatsapp_to", "+351910298749"),
        ("alert_last_session_id", ""),
    ]
    for key, value in defaults:
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


async def init_db() -> None:
    """Drop and recreate usage_records table, create auxiliary tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            DROP TABLE IF EXISTS usage_records;

            CREATE TABLE IF NOT EXISTS usage_records (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                provider             TEXT NOT NULL,
                model                TEXT NOT NULL,
                date                 TEXT NOT NULL,      -- YYYY-MM-DD
                hour                 INTEGER NOT NULL DEFAULT 0,  -- 0-23 UTC
                input_tokens         INTEGER DEFAULT 0,
                output_tokens        INTEGER DEFAULT 0,
                cache_read_tokens    INTEGER DEFAULT 0,
                cache_write_tokens   INTEGER DEFAULT 0,
                real_tokens          INTEGER DEFAULT 0,  -- input + output (billable)
                request_count        INTEGER DEFAULT 0,
                estimated_cost_usd   REAL    DEFAULT 0.0,
                synced_at            TEXT NOT NULL,
                UNIQUE(provider, model, date, hour)
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                provider    TEXT NOT NULL,
                status      TEXT NOT NULL,       -- 'ok' | 'error'
                message     TEXT,
                synced_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_pricing (
                model              TEXT PRIMARY KEY,
                display_name       TEXT,
                input_per_m        REAL DEFAULT 0.0,
                output_per_m       REAL DEFAULT 0.0,
                cache_read_per_m   REAL DEFAULT 0.0,
                cache_write_per_m  REAL DEFAULT 0.0,
                updated_at         TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_usage_date
                ON usage_records(date);

            CREATE INDEX IF NOT EXISTS idx_usage_provider
                ON usage_records(provider);
        """)
        await seed_default_pricing(db)
        await seed_default_settings(db)
        await db.commit()

    logger.info("Database ready at %s", DB_PATH)


async def upsert_usage_record(db: aiosqlite.Connection, record: dict) -> None:
    """Insert or update a usage record (conflict on provider+model+date+hour)."""
    await db.execute("""
        INSERT INTO usage_records
            (provider, model, date, hour, input_tokens, output_tokens, cache_read_tokens,
             cache_write_tokens, real_tokens, request_count, estimated_cost_usd, synced_at)
        VALUES
            (:provider, :model, :date, :hour, :input_tokens, :output_tokens, :cache_read_tokens,
             :cache_write_tokens, :real_tokens, :request_count, :estimated_cost_usd, :synced_at)
        ON CONFLICT(provider, model, date, hour) DO UPDATE SET
            input_tokens        = excluded.input_tokens,
            output_tokens       = excluded.output_tokens,
            cache_read_tokens   = excluded.cache_read_tokens,
            cache_write_tokens  = excluded.cache_write_tokens,
            real_tokens         = excluded.real_tokens,
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


async def get_all_pricing(db: aiosqlite.Connection) -> list:
    """Return all model_pricing rows ordered by model name."""
    rows = await (await db.execute(
        "SELECT * FROM model_pricing ORDER BY model ASC"
    )).fetchall()
    return rows


async def upsert_pricing(
    db: aiosqlite.Connection,
    model: str,
    display_name: str,
    input_per_m: float,
    output_per_m: float,
    cache_read_per_m: float,
    cache_write_per_m: float,
) -> None:
    """Insert or replace a model pricing row."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await db.execute(
        """
        INSERT OR REPLACE INTO model_pricing
            (model, display_name, input_per_m, output_per_m, cache_read_per_m, cache_write_per_m, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (model, display_name, input_per_m, output_per_m, cache_read_per_m, cache_write_per_m, now),
    )


async def delete_pricing(db: aiosqlite.Connection, model: str) -> int:
    """Delete a model pricing row. Returns number of rows deleted."""
    cursor = await db.execute("DELETE FROM model_pricing WHERE model = ?", (model,))
    return cursor.rowcount
