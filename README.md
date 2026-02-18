# OpenClaw Usage Dashboard

A standalone web application that tracks AI token usage and estimated cost across all model providers configured in OpenClaw (Anthropic, Google Gemini, Moonshot/Kimi).

No AI calls. No provider billing APIs required. Pure log parsing from the OpenClaw log file.

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Storage | SQLite via aiosqlite |
| Scheduler | APScheduler (async) |
| Frontend | Jinja2 + Chart.js (CDN) |
| Deployment | Docker container |

## How It Works

All providers use the same data source: `~/.openclaw/logs/openclaw.log`.

OpenClaw writes structured JSON log lines for every model call, including token counts. The dashboard parses those log lines, groups them by `(provider, model, date)`, and stores aggregates in a local SQLite database. A sync runs on startup and every 6 hours thereafter.

### Provider Detection

Provider API keys are used **only** to detect whether a provider is configured. They are not used for any API calls.

| Provider | Detection Env Var | Model Prefix | Method |
|---|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-*` | Log parser |
| Google Gemini | `GEMINI_API_KEY` | `gemini-*` | Log parser |
| Moonshot/Kimi | `MOONSHOT_API_KEY` | `kimi-*`, `moonshot-*` | Log parser |

### Future: Anthropic REST API

If Anthropic releases a usage API accessible to individual accounts, or if you upgrade to a Team/Enterprise plan:

1. Generate an Admin Key at `console.anthropic.com → API Keys → Admin Keys`
2. Set `ANTHROPIC_ADMIN_KEY` in your `.env`
3. Implement the REST fetch in `app/providers/anthropic_provider.py`:
   - `GET https://api.anthropic.com/v1/organizations/usage`
   - Headers: `x-api-key: {ANTHROPIC_ADMIN_KEY}`, `anthropic-version: 2023-06-01`
   - Params: `start_time`, `end_time` (ISO 8601), `group_by=model`
4. Gate on `ANTHROPIC_ADMIN_KEY`: if set → use API, else → fall back to log parsing.

## Setup

### Local (without Docker)

```bash
cd /home/ric/projects/20260218_OpenClaw_Usage
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set ANTHROPIC_API_KEY, GEMINI_API_KEY, MOONSHOT_API_KEY to match your OpenClaw config

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Dashboard available at `http://localhost:8001`

### Docker (standalone)

```bash
cp .env.example .env
# Fill in API keys

docker compose up -d
```

Dashboard available at `http://localhost:8001`

### Manual Sync

```bash
# Sync all providers (last 30 days)
python scripts/sync_now.py

# Sync a specific provider
python scripts/sync_now.py --provider anthropic

# Sync last 7 days only
python scripts/sync_now.py --days 7
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key — detection only | — |
| `GEMINI_API_KEY` | Google Gemini API key — detection only | — |
| `MOONSHOT_API_KEY` | Moonshot API key — detection only | — |
| `OPENCLAW_LOG_PATH` | Path to openclaw.log | `~/.openclaw/logs/openclaw.log` |
| `SYNC_INTERVAL_HOURS` | Hours between automatic syncs | `6` |
| `DB_PATH` | SQLite database path | `/app/data/usage.db` |

## Adding a New Provider

1. Create `app/providers/{name}_provider.py` implementing `BaseProvider`
2. Register an instance in `app/providers/__init__.py` → `ALL_PROVIDERS`
3. Add env var(s) to `.env.example` and `docker-compose.yml`

The `ALL_PROVIDERS` list is the single registration point. The rest of the app discovers providers from it automatically.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/usage/summary` | Aggregate totals (all-time, 30d, 7d) |
| `GET` | `/api/usage/by-model` | Per-model breakdown |
| `GET` | `/api/usage/timeline` | Daily totals, last 30 days |
| `GET` | `/api/usage/by-provider` | Totals grouped by provider |
| `GET` | `/api/providers` | Provider list with config status |
| `POST` | `/api/sync` | Trigger manual sync |
| `GET` | `/api/sync/log` | Last 20 sync events |
| `GET` | `/docs` | FastAPI auto-generated API docs |

## Integration with pacheco-lab

To add this service to the main pacheco-lab Docker stack:

1. Copy the `openclaw-usage` service block from `docker-compose.yml` into `/opt/pacheco-lab/docker-compose.yml`
2. Add to `/opt/pacheco-lab/Caddyfile`:
   ```
   http://usage.ricbits.cc {
       reverse_proxy openclaw-usage:8000
   }
   ```
3. Add public hostname `usage.ricbits.cc` in Cloudflare Zero Trust → Networks → Connectors → pacheco-lab → Public Hostnames → `http://caddy:80`
4. Add `usage.ricbits.cc` to Cloudflare Access policy
5. Run: `cd /opt/pacheco-lab && ./update.sh && docker exec caddy caddy reload --config /etc/caddy/Caddyfile`
