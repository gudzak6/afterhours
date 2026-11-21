"""Import Garmin activity summaries. Duplicate Garmin activity IDs are updated in place."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.garmin.client import GarminConfigurationError, GarminRequestError, GarminSession
from app.garmin.connect import GarminConnectSession
from app.garmin.mapping import ActivityMappingError, normalize_activity
from app.models import Activity, Athlete, Coach, GarminConnection, SyncJob

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()


class SyncInProgress(RuntimeError):
    pass


def ensure_coach(session: Session, settings: Settings) -> Coach:
    coach = session.scalar(select(Coach).order_by(Coach.id).limit(1))
    now = datetime.now(UTC)
    if coach is None:
        coach = Coach(
            display_name="Coach Owen",
            timezone="America/New_York",
            email_notifications_enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(coach)
        session.commit()
        session.refresh(coach)
    unassigned = session.scalars(select(Athlete).where(Athlete.coach_id.is_(None))).all()
    if unassigned:
        for athlete in unassigned:
            athlete.coach_id = coach.id
        session.commit()
    return coach


def athletes_for_coach(session: Session, coach: Coach) -> list[Athlete]:
    return list(
        session.scalars(select(Athlete).where(Athlete.coach_id == coach.id).order_by(Athlete.display_name, Athlete.id)).all()
    )


def ensure_athlete(session: Session, settings: Settings) -> Athlete:
    coach = ensure_coach(session, settings)
    athlete = session.scalar(
        select(Athlete).where(Athlete.coach_id == coach.id).order_by(Athlete.id).limit(1)
    )
    if athlete is not None:
        return athlete
    now = datetime.now(UTC)
    athlete = Athlete(
        coach_id=coach.id,
        display_name=settings.athlete_display_name,
        created_at=now,
        updated_at=now,
    )
    session.add(athlete)
    session.commit()
    session.refresh(athlete)
    return athlete


def record_connection(
    session: Session,
    athlete: Athlete,
    *,
    status: str,
    token_expires_at: datetime | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now(UTC)
    connection = session.scalar(
        select(GarminConnection).where(GarminConnection.athlete_id == athlete.id)
    )
    if connection is None:
        connection = GarminConnection(
            athlete_id=athlete.id,
            status=status,
            updated_at=now,
        )
        session.add(connection)
    connection.status = status
    connection.updated_at = now
    connection.last_error = error
    if token_expires_at is not None:
        connection.token_expires_at = token_expires_at
        connection.last_authenticated_at = now
    session.commit()


def _remember_connect_token(session: Session, athlete_id: int, gateway: object) -> None:
    dump = getattr(gateway, "dumps", None)
    if not callable(dump):
        return
    connection = session.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete_id))
    if connection is None:
        return
    try:
        connection.connect_token = dump()
    except Exception:
        logger.info("Garmin session for athlete %s was left unchanged", athlete_id)
        return
    session.commit()


def scrub_key(text: str | None, api_key: str | None) -> str | None:
    if text is None or not api_key:
        return text
    return text.replace(api_key, "[redacted]")


def reapply_athlete_overrides(activity: Activity) -> None:
    overrides = activity.athlete_overrides or {}
    if not isinstance(overrides, dict):
        return
    for column in (
        "name",
        "distance_meters",
        "duration_seconds",
        "moving_duration_seconds",
        "average_heart_rate_bpm",
        "max_heart_rate_bpm",
        "average_speed_mps",
    ):
        if column in overrides:
            setattr(activity, column, overrides[column])


def run_sync(
    session: Session,
    settings: Settings,
    *,
    trigger: str,
    lookback_days: int | None = None,
    activity_type: str | None = None,
    athlete_id: int | None = None,
    api_key: str | None = None,
    connect_token: str | None = None,
) -> SyncJob:
    if not _SYNC_LOCK.acquire(blocking=False):
        if trigger == "scheduled":
            raise SyncInProgress("scheduled sync skipped because a sync is already running")
        raise SyncInProgress("A Garmin sync is already running")

    try:
        return _run_sync_locked(
            session,
            settings,
            trigger=trigger,
            lookback_days=lookback_days,
            activity_type=activity_type,
            athlete_id=athlete_id,
            api_key=api_key,
            connect_token=connect_token,
        )
    finally:
        _SYNC_LOCK.release()


def sync_saved_athlete_keys(session: Session, settings: Settings) -> list[SyncJob]:
    """Import activities for athletes who signed in, or who still have a saved key."""
    rows = session.scalars(select(GarminConnection)).all()
    jobs: list[SyncJob] = []
    for row in rows:
        token = (row.connect_token or "").strip()
        key = (row.personal_api_key or "").strip()
        if not token and not key:
            continue
        try:
            jobs.append(
                run_sync(
                    session,
                    settings,
                    trigger="scheduled",
                    athlete_id=row.athlete_id,
                    api_key=None if token else key,
                    connect_token=token or None,
                )
            )
        except SyncInProgress:
            logger.info("Athlete Garmin sync skipped because another sync is running")
            break
    return jobs


def _run_sync_locked(
    session: Session,
    settings: Settings,
    *,
    trigger: str,
    lookback_days: int | None,
    activity_type: str | None,
    athlete_id: int | None,
    api_key: str | None,
    connect_token: str | None = None,
) -> SyncJob:
    if connect_token:
        if athlete_id is None:
            raise GarminConfigurationError("That athlete is not on this roster.")
        athlete = session.get(Athlete, athlete_id)
        if athlete is None:
            raise GarminConfigurationError("That athlete is not on this roster.")
        gateway = GarminConnectSession(connect_token)
    elif athlete_id is None:
        athlete = ensure_athlete(session, settings)
        gateway = GarminSession(settings)
    else:
        athlete = session.get(Athlete, athlete_id)
        if athlete is None:
            raise GarminConfigurationError("That athlete is not on this roster.")
        cache = settings.garmin_token_cache_path.parent / f"garmin-bearer-{athlete.id}.json"
        gateway = GarminSession(settings, api_key=api_key, token_cache_path=cache if api_key else None)
    days = lookback_days if lookback_days is not None else settings.garmin_sync_lookback_days
    now = datetime.now(UTC)
    job = SyncJob(
        athlete_id=athlete.id,
        trigger=trigger,
        status="running",
        started_at=now,
        lookback_days=days,
        activities_seen=0,
        activities_imported=0,
        activities_updated=0,
        activities_skipped=0,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Garmin treats the end date as the first day to leave out, so add a day
    # or a run from today is skipped.
    end = now.date() + timedelta(days=1)
    start = end - timedelta(days=days)
    offset = 0
    page_size = max(1, min(settings.garmin_sync_page_size, 100))
    try:
        while offset < settings.garmin_sync_max_activities:
            limit = min(page_size, settings.garmin_sync_max_activities - offset)
            page = gateway.search_activities(
                start=offset,
                limit=limit,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                activity_type=activity_type,
            )
            if page is None:
                break
            if not isinstance(page, list):
                raise GarminRequestError(
                    "Garmin activity search did not return a list",
                    code="garmin_unexpected_payload",
                )
            if not page:
                break
            for item in page:
                outcome = _upsert_activity(session, athlete, item)
                job.activities_seen += 1
                if outcome == "imported":
                    job.activities_imported += 1
                elif outcome == "updated":
                    job.activities_updated += 1
                else:
                    job.activities_skipped += 1
            session.commit()
            offset += len(page)
            if len(page) < limit:
                break
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        session.commit()
        _remember_connect_token(session, athlete.id, gateway)
        record_connection(
            session,
            athlete,
            status="connected",
            token_expires_at=gateway.token_expires_at,
            error=None,
        )
        logger.info(
            "Garmin sync %s finished: seen=%s imported=%s updated=%s skipped=%s",
            job.id,
            job.activities_seen,
            job.activities_imported,
            job.activities_updated,
            job.activities_skipped,
        )
        from app.fit.importer import start_file_import

        start_file_import()
        return job
    except (GarminConfigurationError, GarminRequestError, ActivityMappingError) as exc:
        session.rollback()
        failed = session.get(SyncJob, job.id)
        if failed is None:
            raise
        failed.status = "failed"
        failed.finished_at = datetime.now(UTC)
        if isinstance(exc, GarminConfigurationError):
            failed.error_code = "garmin_not_configured"
            failed.http_status = None
        elif isinstance(exc, GarminRequestError):
            failed.error_code = exc.code
            failed.http_status = exc.http_status
        else:
            failed.error_code = "activity_mapping_error"
        failed.error_message = scrub_key(scrub_key(str(exc), api_key), connect_token)
        session.commit()
        record_connection(
            session,
            athlete,
            status="error" if not isinstance(exc, GarminConfigurationError) else "not_configured",
            error=scrub_key(scrub_key(str(exc), api_key), connect_token),
        )
        logger.info("Garmin sync %s failed: %s", failed.id, failed.error_code)
        return failed


def _upsert_activity(session: Session, athlete: Athlete, item: object) -> str:
    if not isinstance(item, dict):
        logger.info("Skipping Garmin activity because the record is not an object")
        return "skipped"
    try:
        mapped = normalize_activity(item)
    except ActivityMappingError:
        logger.info("Skipping Garmin activity with no positive activityId")
        return "skipped"

    existing = session.scalar(
        select(Activity).where(
            Activity.athlete_id == athlete.id,
            Activity.garmin_activity_id == mapped["garmin_activity_id"],
        )
    )
    now = datetime.now(UTC)
    columns = (
        "name",
        "activity_type_key",
        "start_time_local",
        "start_time_gmt",
        "start_time_utc",
        "distance_meters",
        "duration_seconds",
        "moving_duration_seconds",
        "elapsed_duration_raw",
        "average_speed_mps",
        "max_speed_mps",
        "average_heart_rate_bpm",
        "max_heart_rate_bpm",
        "elevation_gain_meters",
        "elevation_loss_meters",
        "average_cadence_spm",
        "calories",
        "lap_count",
        "start_latitude",
        "start_longitude",
        "location_name",
        "manual_activity",
        "present_fields",
        "raw_summary",
    )
    if existing is None:
        session.add(
            Activity(
                athlete_id=athlete.id,
                garmin_activity_id=mapped["garmin_activity_id"],
                import_status="summary_only",
                created_at=now,
                updated_at=now,
                **{column: mapped[column] for column in columns},
            )
        )
        return "imported"
    for column in columns:
        setattr(existing, column, mapped[column])
    existing.updated_at = now
    reapply_athlete_overrides(existing)
    return "updated"
