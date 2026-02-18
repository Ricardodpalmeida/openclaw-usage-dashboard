"""
OpenClaw Usage Dashboard — FastAPI application entrypoint.

Startup sequence:
  1. Load .env (if present)
  2. Initialise SQLite database
  3. Run initial full sync (background task)
  4. Start APScheduler for recurring syncs
  5. Mount Jinja2 template renderer
  6. Register API routers

Dashboard served at GET /
API docs at GET /docs
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .database import init_db
from .scheduler import start_scheduler, sync_all
from .routers.usage_router import router as usage_router
from .routers.provider_router import router as provider_router

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenClaw Usage Dashboard",
    description="Token usage tracking across all AI model providers via log parsing.",
    version="1.0.0",
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
async def on_startup():
    await init_db()
    start_scheduler()
    # Run initial sync without blocking startup
    asyncio.create_task(sync_all())
    logger.info("OpenClaw Usage Dashboard started")


@app.on_event("shutdown")
async def on_shutdown():
    from .scheduler import scheduler
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app.include_router(usage_router)
app.include_router(provider_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the single-page dashboard."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok"}
