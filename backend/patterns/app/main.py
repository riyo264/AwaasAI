"""FastAPI application factory.

Wires together the routers (events, state, patterns, context, admin) into a
single ASGI app served by uvicorn inside an ECS container behind an ALB.

The deterministic pattern-extraction job runs as an in-process background
scheduler (see ``_extraction_scheduler``) so the whole platform is one
self-contained service — no external scheduler or extra runtime required.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from patterns.app.config import get_settings
from patterns.routes import admin, ambient, context, context_notes, events, patterns, profile, state

logger = logging.getLogger(__name__)


async def _extraction_scheduler() -> None:
    """Periodically re-learn patterns for the configured households.

    This replaces a scheduled job (cron / external trigger): the same
    ``pattern_service.extract_and_store`` logic exposed by
    ``POST /patterns/{id}/extract`` runs automatically on a fixed interval.
    Dormant when ``SCHEDULED_HOUSEHOLD_IDS`` is empty.
    """
    settings = get_settings()
    household_ids = [
        h.strip() for h in settings.scheduled_household_ids.split(",") if h.strip()
    ]
    if not household_ids:
        return  # scheduler disabled

    interval_seconds = max(60.0, settings.extraction_interval_hours * 3600.0)
    from patterns.logic import pattern_service

    while True:
        await asyncio.sleep(interval_seconds)
        for household_id in household_ids:
            try:
                patterns = await asyncio.to_thread(
                    pattern_service.extract_and_store, household_id
                )
                logger.info(
                    "Scheduled extraction: %s -> %d patterns",
                    household_id,
                    len(patterns),
                )
            except Exception:  # never let one failure kill the loop
                logger.exception("Scheduled extraction failed for %s", household_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In local/dev we ensure tables exist on startup. In AWS the tables are
    # created by IaC, and create_tables() is a no-op because they already exist.
    try:
        from patterns.dynamodb.tables import create_tables

        create_tables()
    except Exception:  # pragma: no cover - never block startup on table check
        pass

    # Start the in-process extraction scheduler (dormant if unconfigured).
    task = asyncio.create_task(_extraction_scheduler())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # pragma: no cover
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Context-Aware Smart Home Intelligence Platform",
        version="0.1.0",
        description=(
            "MVP: event collection -> storage -> state -> deterministic pattern "
            "extraction -> AI-ready context object (Bedrock hand-off, future phase)."
        ),
        lifespan=lifespan,
    )

    # Allow the React dev server (and any local origin) to call the API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(events.router)
    app.include_router(state.router)
    app.include_router(patterns.router)
    app.include_router(context.router)
    app.include_router(context_notes.router)
    app.include_router(profile.router)
    app.include_router(admin.router)
    app.include_router(ambient.router)
    return app


app = create_app()
