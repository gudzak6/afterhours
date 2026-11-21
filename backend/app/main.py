"""FastAPI application for the local running coach."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.platform import router as platform_router
from app.api.platform import run_notification_job
from app.api.portal import router as portal_router
from app.api.routes import router
from app.config import BACKEND_ROOT, get_settings
from app.database import SessionLocal
from app.services.sync import SyncInProgress, run_sync, sync_saved_athlete_keys

logger = logging.getLogger("trainingcoach")
_scheduler: BackgroundScheduler | None = None


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # The official client logs request paths. Keep it quieter than our sync summaries.
    logging.getLogger("garmin_personal_api").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _migrate() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


def _scheduled_sync() -> None:
    settings = get_settings()
    if not settings.garmin_key_configured:
        logger.info("Scheduled Garmin sync skipped because no API key is configured")
        return
    session = SessionLocal()
    try:
        if settings.garmin_key_configured:
            try:
                run_sync(session, settings, trigger="scheduled")
            except SyncInProgress:
                logger.info("Scheduled Garmin sync skipped because another sync is running")
        try:
            sync_saved_athlete_keys(session, settings)
        except SyncInProgress:
            logger.info("Athlete Garmin sync skipped because another sync is running")
    finally:
        session.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _scheduler
    _configure_logging()
    _migrate()
    settings = get_settings()
    _scheduler = BackgroundScheduler(daemon=True)
    if settings.garmin_sync_interval_minutes > 0:
        _scheduler.add_job(
            _scheduled_sync,
            "interval",
            minutes=settings.garmin_sync_interval_minutes,
            id="garmin-sync",
            coalesce=True,
            max_instances=1,
        )
        logger.info(
            "Automatic Garmin sync scheduled every %s minutes",
            settings.garmin_sync_interval_minutes,
        )
    else:
        logger.info("Automatic Garmin sync is disabled")
    _scheduler.add_job(
        run_notification_job,
        "interval",
        hours=1,
        id="coaching-brief-email",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="Training Coach", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.include_router(platform_router)
    application.include_router(portal_router)

    @application.exception_handler(Exception)
    async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled API error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "The API hit an unexpected error before it could return JSON.",
                }
            },
        )

    return application


app = create_app()
