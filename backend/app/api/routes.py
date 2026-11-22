"""HTTP API for Garmin sync and stored activities."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.coach.engine import chat, generate_report, openai_configured, present_report, safe_error
from app.fit.importer import file_import_status, import_one, start_file_import
from app.garmin.mapping import METERS_PER_MILE, pace_seconds_per_mile
from app.metrics.engine import activity_metrics
from app.models import (
    Activity,
    ActivityFile,
    ActivityLap,
    ActivitySample,
    ActivityWorkoutStep,
    AiConversation,
    AiMessage,
    Athlete,
    AthleteThreshold,
    GarminConnection,
    SyncJob,
    TrainingGoal,
    WorkoutAnalysis,
    WorkoutClassification,
    WorkoutSegment,
)
from app.schemas import (
    ActivityDetailOut,
    ActivityListOut,
    ActivityOut,
    AthleteIntake,
    AthleteOut,
    AthleteUpdate,
    stored_intake,
    ChatRequest,
    ChatResponse,
    ChatMessageOut,
    ClassificationOut,
    ClassificationUpdate,
    FileImportStatus,
    GarminStatusOut,
    LapOut,
    SegmentOut,
    SeriesPoint,
    SyncJobOut,
    SyncRequest,
    ThresholdOut,
    TrainingSummaryOut,
    TrainingWindow,
    WeeklyMileage,
)
from app.services.history import training_history
from app.services.mileage import window_stats
from app.services.sync import SyncInProgress, athletes_for_coach, ensure_athlete, ensure_coach, run_sync

router = APIRouter()

FIT_DOWNLOAD_NOTE = (
    "Original files are downloaded with the official client method download_activity, "
    "which calls GET /download-service/files/activity/{activity_id} and returns a ZIP. "
    "A 404 is stored as file_unavailable. A 403 would mean this key cannot download original files."
)


def _classification_map(db: Session, activity_ids: list[int]) -> dict[int, WorkoutClassification]:
    if not activity_ids:
        return {}
    rows = db.scalars(
        select(WorkoutClassification).where(WorkoutClassification.activity_id.in_(activity_ids))
    ).all()
    return {row.activity_id: row for row in rows}


def _analysis_status_map(db: Session, activity_ids: list[int]) -> dict[int, str]:
    if not activity_ids:
        return {}
    rows = db.scalars(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id.in_(activity_ids))
        .order_by(WorkoutAnalysis.id)
    ).all()
    return {row.activity_id: row.status for row in rows}


def _activity_out(
    activity: Activity,
    *,
    include_location: bool,
    classification: WorkoutClassification | None,
    analysis_status: str,
    athlete_name: str | None = None,
) -> ActivityOut:
    return ActivityOut.from_activity(
        activity,
        include_location=include_location,
        workout_type=None if classification is None else classification.workout_type,
        classification_source=None if classification is None else classification.source,
        analysis_status=analysis_status,
        athlete_name=athlete_name,
    )


def _owned_athlete_ids(db: Session, settings: Settings) -> list[int]:
    coach = ensure_coach(db, settings)
    return [athlete.id for athlete in athletes_for_coach(db, coach)]


def _athlete_out(db: Session, athlete: Athlete, settings: Settings) -> AthleteOut:
    goal = db.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
    thresholds = db.scalars(
        select(AthleteThreshold).where(AthleteThreshold.athlete_id == athlete.id).order_by(AthleteThreshold.name)
    ).all()
    preferences = athlete.workout_preferences or {}
    return AthleteOut(
        id=athlete.id,
        display_name=athlete.display_name,
        running_experience=athlete.running_experience,
        typical_weekly_mileage=athlete.typical_weekly_mileage,
        max_heart_rate_bpm=athlete.max_heart_rate_bpm,
        preferred_training_days=list(athlete.preferred_training_days or []),
        pace_zones=list(preferences.get("pace_zones") or []),
        heart_rate_zones=list(preferences.get("heart_rate_zones") or []),
        primary_race_goal=None if goal is None else goal.primary_race_goal,
        goal_race_date=None if goal is None else goal.goal_race_date,
        target_time=athlete.target_time,
        coach_notes=athlete.coach_notes,
        intake=AthleteIntake.model_validate(athlete.intake or {}),
        thresholds=[
            ThresholdOut(
                name=row.name,
                pace_seconds_per_mile=row.pace_seconds_per_mile,
                heart_rate_bpm=row.heart_rate_bpm,
                source=row.source,
            )
            for row in thresholds
        ],
        openai_configured=openai_configured(settings),
    )


def _downsample(samples: list[ActivitySample], max_points: int = 450) -> list[ActivitySample]:
    if len(samples) <= max_points:
        return samples
    step = len(samples) / max_points
    picked = [samples[min(len(samples) - 1, int(index * step))] for index in range(max_points)]
    if picked[-1] is not samples[-1]:
        picked[-1] = samples[-1]
    return picked


def _series_point(sample: ActivitySample) -> SeriesPoint:
    return SeriesPoint(
        elapsed_seconds=sample.elapsed_seconds,
        distance_meters=sample.distance_meters,
        pace_seconds_per_mile=pace_seconds_per_mile(sample.speed_mps),
        heart_rate_bpm=sample.heart_rate_bpm,
        altitude_meters=sample.altitude_meters,
        cadence=sample.cadence_spm,
    )


def _sync_status_code(job: SyncJob) -> int:
    if job.status == "succeeded":
        return 200
    if job.error_code == "garmin_not_configured":
        return 503
    if job.error_code == "garmin_unauthorized":
        return 401
    if job.error_code == "garmin_rate_limited":
        return 429
    return 502


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/athlete", response_model=AthleteOut)
def get_athlete(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AthleteOut:
    return _athlete_out(db, ensure_athlete(db, settings), settings)


def apply_athlete_update(db: Session, settings: Settings, athlete: Athlete, body: AthleteUpdate) -> AthleteOut:
    changes = body.model_dump(exclude_unset=True)
    if "display_name" in changes and changes["display_name"]:
        athlete.display_name = changes["display_name"].strip()
    for field in (
        "running_experience",
        "typical_weekly_mileage",
        "max_heart_rate_bpm",
        "preferred_training_days",
        "target_time",
        "coach_notes",
    ):
        if field in changes:
            setattr(athlete, field, changes[field])
    if "pace_zones" in changes or "heart_rate_zones" in changes:
        preferences = dict(athlete.workout_preferences or {})
        if "pace_zones" in changes:
            preferences["pace_zones"] = changes["pace_zones"] or []
        if "heart_rate_zones" in changes:
            preferences["heart_rate_zones"] = changes["heart_rate_zones"] or []
        athlete.workout_preferences = preferences
    if "primary_race_goal" in changes or "goal_race_date" in changes:
        goal = db.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
        if goal is None:
            goal = TrainingGoal(athlete_id=athlete.id, updated_at=datetime.now(UTC))
            db.add(goal)
        if "primary_race_goal" in changes:
            goal.primary_race_goal = changes["primary_race_goal"]
        if "goal_race_date" in changes:
            goal.goal_race_date = changes["goal_race_date"]
        goal.updated_at = datetime.now(UTC)
    if "intake" in body.model_fields_set:
        stored = None if body.intake is None else stored_intake(body.intake)
        athlete.intake = stored
        if stored is not None:
            full_name = " ".join(part for part in (stored.get("first_name"), stored.get("last_name")) if part)
            if full_name:
                athlete.display_name = full_name[:120]
    if "thresholds" in changes:
        for item in body.thresholds or []:
            row = db.scalar(
                select(AthleteThreshold).where(
                    AthleteThreshold.athlete_id == athlete.id,
                    AthleteThreshold.name == item.name.strip(),
                )
            )
            if row is None:
                row = AthleteThreshold(
                    athlete_id=athlete.id,
                    name=item.name.strip(),
                    source="user",
                    updated_at=datetime.now(UTC),
                )
                db.add(row)
            row.pace_seconds_per_mile = item.pace_seconds_per_mile
            row.heart_rate_bpm = item.heart_rate_bpm
            row.source = "user"
            row.updated_at = datetime.now(UTC)
    athlete.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(athlete)
    return _athlete_out(db, athlete, settings)


@router.patch("/api/athlete", response_model=AthleteOut)
def update_athlete(
    body: AthleteUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AthleteOut:
    return apply_athlete_update(db, settings, ensure_athlete(db, settings), body)


@router.get("/api/garmin/status", response_model=GarminStatusOut)
def garmin_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GarminStatusOut:
    athlete = ensure_athlete(db, settings)
    connection = db.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
    last_job = db.scalar(
        select(SyncJob)
        .where(SyncJob.athlete_id == athlete.id)
        .order_by(SyncJob.started_at.desc(), SyncJob.id.desc())
        .limit(1)
    )
    if not settings.garmin_key_configured:
        status = "not_configured"
    elif connection is not None:
        status = connection.status
    else:
        status = "not_connected"
    return GarminStatusOut(
        configured=settings.garmin_key_configured,
        connection_status=status,
        token_cached=settings.garmin_token_cache_path.exists(),
        token_expires_at=connection.token_expires_at if connection else None,
        last_error=connection.last_error if connection else None,
        scheduler_enabled=settings.garmin_sync_interval_minutes > 0 and settings.garmin_key_configured,
        scheduler_interval_minutes=settings.garmin_sync_interval_minutes,
        fit_download_documented=True,
        fit_download_implemented=True,
        fit_download_note=FIT_DOWNLOAD_NOTE,
        last_sync=SyncJobOut.from_job(last_job) if last_job else None,
    )


@router.post("/api/garmin/sync", response_model=SyncJobOut)
def sync_garmin(
    body: SyncRequest = Body(default_factory=SyncRequest),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SyncJobOut:
    request = body
    try:
        job = run_sync(
            db,
            settings,
            trigger="manual",
            lookback_days=request.lookback_days,
            activity_type=request.activity_type,
        )
    except SyncInProgress as exc:
        raise HTTPException(status_code=409, detail={"code": "sync_in_progress", "message": str(exc)}) from exc
    payload = SyncJobOut.from_job(job)
    status_code = _sync_status_code(job)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=payload.model_dump(mode="json"))
    return payload


@router.get("/api/activities", response_model=ActivityListOut)
def list_activities(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    activity_type: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ActivityListOut:
    ensure_athlete(db, settings)
    owned_ids = _owned_athlete_ids(db, settings)
    names = {
        athlete.id: athlete.display_name
        for athlete in db.scalars(select(Athlete).where(Athlete.id.in_(owned_ids or [0]))).all()
    }
    filters = [Activity.athlete_id.in_(owned_ids or [0])]
    if activity_type:
        filters.append(Activity.activity_type_key == activity_type)
    total = db.scalar(select(func.count()).select_from(Activity).where(*filters)) or 0
    rows = db.scalars(
        select(Activity)
        .where(*filters)
        .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc(), Activity.garmin_activity_id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    classifications = _classification_map(db, [row.id for row in rows])
    analyses = _analysis_status_map(db, [row.id for row in rows])
    return ActivityListOut(
        total=total,
        activities=[
            _activity_out(
                row,
                include_location=False,
                classification=classifications.get(row.id),
                analysis_status=analyses.get(row.id, "not_started"),
                athlete_name=names.get(row.athlete_id),
            )
            for row in rows
        ],
    )


def _load_activity(db: Session, athlete: Athlete, activity_id: int, owner_id: int | None = None) -> Activity:
    owned_ids = [athlete.id]
    if athlete.coach_id is not None:
        owned_ids = list(db.scalars(select(Athlete.id).where(Athlete.coach_id == athlete.coach_id)).all())
    if owner_id is not None:
        if owner_id not in owned_ids:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Activity not found"})
        owned_ids = [owner_id]
    rows = list(
        db.scalars(
            select(Activity)
            .where(
                Activity.athlete_id.in_(owned_ids or [0]),
                Activity.garmin_activity_id == activity_id,
            )
            .order_by(Activity.athlete_id)
        ).all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Activity not found"})
    if owner_id is None and len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ambiguous_activity",
                "message": "This activity is stored for more than one athlete. Open it from that athlete.",
            },
        )
    return rows[0]


@router.get("/api/activities/{activity_id}", response_model=ActivityDetailOut)
def get_activity(
    activity_id: int,
    athlete_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ActivityDetailOut:
    athlete = ensure_athlete(db, settings)
    activity = _load_activity(db, athlete, activity_id, athlete_id)
    owner = db.get(Athlete, activity.athlete_id)
    laps = db.scalars(
        select(ActivityLap).where(ActivityLap.activity_id == activity.id).order_by(ActivityLap.lap_number)
    ).all()
    samples = db.scalars(
        select(ActivitySample)
        .where(ActivitySample.activity_id == activity.id)
        .order_by(ActivitySample.elapsed_seconds.is_(None), ActivitySample.elapsed_seconds)
    ).all()
    segments = db.scalars(
        select(WorkoutSegment)
        .where(WorkoutSegment.activity_id == activity.id)
        .order_by(WorkoutSegment.segment_index)
    ).all()
    classification = db.scalar(
        select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id)
    )
    analysis = db.scalar(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id == activity.id)
        .order_by(WorkoutAnalysis.id.desc())
        .limit(1)
    )
    preferences = athlete.workout_preferences or {}
    lap_dicts = []
    for lap in laps:
        raw = lap.raw_lap or {}
        lap_dicts.append(
            {
                "lap_number": lap.lap_number,
                "distance_meters": lap.distance_meters,
                "duration_seconds": lap.duration_seconds,
                "average_speed_mps": lap.average_speed_mps,
                "average_heart_rate_bpm": lap.average_heart_rate_bpm,
                "max_heart_rate_bpm": lap.max_heart_rate_bpm,
            }
        )
    sample_dicts = [
        {
            "elapsed_seconds": sample.elapsed_seconds,
            "distance_meters": sample.distance_meters,
            "speed_mps": sample.speed_mps,
            "heart_rate_bpm": sample.heart_rate_bpm,
            "altitude_meters": sample.altitude_meters,
        }
        for sample in samples
    ]
    metrics = activity_metrics(
        lap_dicts,
        sample_dicts,
        classification=None
        if classification is None
        else {"evidence": classification.evidence, "workout_type": classification.workout_type},
        pace_zones=preferences.get("pace_zones") or None,
        heart_rate_zones=preferences.get("heart_rate_zones") or None,
        elevation_gain_meters=activity.elevation_gain_meters,
        elevation_loss_meters=activity.elevation_loss_meters,
    )
    step_count = db.scalar(
        select(func.count()).select_from(ActivityWorkoutStep).where(ActivityWorkoutStep.activity_id == activity.id)
    ) or 0
    return ActivityDetailOut(
        activity=_activity_out(
            activity,
            include_location=True,
            classification=classification,
            analysis_status="not_started" if analysis is None else analysis.status,
            athlete_name=None if owner is None else owner.display_name,
        ),
        laps=[
            LapOut(
                lap_number=lap.lap_number,
                distance_meters=lap.distance_meters,
                distance_miles=None if lap.distance_meters is None else lap.distance_meters / METERS_PER_MILE,
                duration_seconds=lap.duration_seconds,
                pace_seconds_per_mile=pace_seconds_per_mile(lap.average_speed_mps),
                average_speed_mps=lap.average_speed_mps,
                average_heart_rate_bpm=lap.average_heart_rate_bpm,
                max_heart_rate_bpm=lap.max_heart_rate_bpm,
                average_cadence=lap.average_cadence_spm,
                cadence_field=(lap.raw_lap or {}).get("cadence_field"),
                intensity=(lap.raw_lap or {}).get("intensity"),
                lap_trigger=(lap.raw_lap or {}).get("lap_trigger"),
                present_fields=list(lap.present_fields or []),
            )
            for lap in laps
        ],
        segments=[
            SegmentOut(
                segment_index=segment.segment_index,
                kind=segment.kind,
                start_lap=segment.start_lap,
                end_lap=segment.end_lap,
                lap_numbers=list((segment.evidence or {}).get("lap_numbers") or []),
                confidence=segment.confidence,
                source=segment.source,
            )
            for segment in segments
        ],
        classification=None
        if classification is None
        else ClassificationOut(
            workout_type=classification.workout_type,
            confidence=classification.confidence,
            source=classification.source,
            uncertainty=classification.uncertainty,
            evidence=classification.evidence or {},
        ),
        metrics=metrics,
        series=[_series_point(sample) for sample in _downsample(list(samples))],
        report=present_report(
            None if analysis is None else analysis.report,
            workout_type=None if classification is None else classification.workout_type,
            distance_meters=activity.distance_meters,
            average_speed_mps=activity.average_speed_mps,
        ),
        report_status="not_started" if analysis is None else analysis.status,
        fit_summary=activity.fit_summary,
        workout_steps_found=step_count > 0,
    )


@router.delete("/api/activities/{activity_id}", status_code=204)
def delete_activity(
    activity_id: int,
    athlete_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    athlete = ensure_athlete(db, settings)
    activity = _load_activity(db, athlete, activity_id, athlete_id)
    conversation_ids = list(
        db.scalars(select(AiConversation.id).where(AiConversation.activity_id == activity.id)).all()
    )
    if conversation_ids:
        db.execute(delete(AiMessage).where(AiMessage.conversation_id.in_(conversation_ids)))
        db.execute(delete(AiConversation).where(AiConversation.id.in_(conversation_ids)))
    for model in (
        ActivitySample,
        ActivityLap,
        ActivityWorkoutStep,
        ActivityFile,
        WorkoutSegment,
        WorkoutClassification,
        WorkoutAnalysis,
    ):
        db.execute(delete(model).where(model.activity_id == activity.id))
    db.delete(activity)
    db.commit()


@router.get("/api/training/summary", response_model=TrainingSummaryOut)
def training_summary(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrainingSummaryOut:
    athlete = ensure_athlete(db, settings)
    activities = list(db.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    now = datetime.now(UTC)

    def window(days: int) -> TrainingWindow:
        activity_count, with_distance, distance_meters = window_stats(activities, now=now, days=days)
        return TrainingWindow(
            days=days,
            activity_count=activity_count,
            activities_with_distance=with_distance,
            distance_meters=distance_meters,
            distance_miles=None if distance_meters is None else distance_meters / METERS_PER_MILE,
        )

    classifications = _classification_map(db, [activity.id for activity in activities])
    history = training_history(
        activities,
        {activity_id: row.workout_type for activity_id, row in classifications.items()},
        now=now,
    )
    return TrainingSummaryOut(
        activity_count=len(activities),
        last_7_days=window(7),
        last_28_days=window(28),
        workout_counts=history["workout_counts"],
        hard_workouts_28_days=history["hard_workouts_28_days"],
        active_days_28=history["active_days_28"],
        weekly_mileage=[WeeklyMileage(**bucket) for bucket in history["weekly_mileage"]],
    )


@router.post("/api/garmin/files", response_model=FileImportStatus)
def start_files(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> FileImportStatus:
    if not settings.garmin_key_configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "garmin_not_configured", "message": "Add GARMIN_PERSONAL_API_KEY before downloading files."},
        )
    start_file_import()
    return FileImportStatus(**file_import_status(db))


@router.get("/api/garmin/files", response_model=FileImportStatus)
def files_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> FileImportStatus:
    ensure_athlete(db, settings)
    return FileImportStatus(**file_import_status(db))


@router.post("/api/activities/{activity_id}/file")
def download_activity_file(
    activity_id: int,
    athlete_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = ensure_athlete(db, settings)
    activity = _load_activity(db, athlete, activity_id, athlete_id)
    result = import_one(db, settings, activity)
    if result == "already_running":
        raise HTTPException(
            status_code=409,
            detail={"code": "import_in_progress", "message": "A file import is already running."},
        )
    db.refresh(activity)
    return {"import_status": activity.import_status}


@router.patch("/api/activities/{activity_id}/classification", response_model=ClassificationOut)
def update_classification(
    activity_id: int,
    body: ClassificationUpdate,
    athlete_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ClassificationOut:
    athlete = ensure_athlete(db, settings)
    activity = _load_activity(db, athlete, activity_id, athlete_id)
    row = db.scalar(select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id))
    now = datetime.now(UTC)
    if row is None:
        row = WorkoutClassification(
            activity_id=activity.id,
            workout_type=body.workout_type.strip(),
            confidence=1.0,
            evidence={"note": "Saved by the athlete."},
            uncertainty=None,
            source="user",
            created_at=now,
        )
        db.add(row)
    else:
        evidence = dict(row.evidence or {})
        evidence["user_override"] = {"previous_type": row.workout_type}
        row.workout_type = body.workout_type.strip()
        row.confidence = 1.0
        row.source = "user"
        row.uncertainty = None
        row.evidence = evidence
        row.created_at = now
    db.commit()
    db.refresh(row)
    return ClassificationOut(
        workout_type=row.workout_type,
        confidence=row.confidence,
        source=row.source,
        uncertainty=row.uncertainty,
        evidence=row.evidence or {},
    )


@router.post("/api/activities/{activity_id}/report")
def create_report(
    activity_id: int,
    athlete_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = ensure_athlete(db, settings)
    activity = _load_activity(db, athlete, activity_id, athlete_id)
    if not openai_configured(settings):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openai_not_configured",
                "message": "Add OPENAI_API_KEY to the API environment to generate a report. No report was invented.",
            },
        )
    owner = db.get(Athlete, activity.athlete_id)
    if owner is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Athlete not found"})
    try:
        row = generate_report(db, settings, owner, activity)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "openai_error", "message": safe_error(exc)},
        ) from exc
    return {"status": row.status, "model": row.model, "report": row.report}


@router.post("/api/coach/chat", response_model=ChatResponse)
def coach_chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    athlete = ensure_athlete(db, settings)
    roster = athletes_for_coach(db, ensure_coach(db, settings)) or [athlete]
    if not openai_configured(settings):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openai_not_configured",
                "message": "Add OPENAI_API_KEY to the API environment. The coach will not invent an answer.",
            },
        )
    try:
        conversation, messages = chat(
            db,
            settings,
            athlete,
            message=body.message,
            conversation_id=body.conversation_id,
            garmin_activity_id=body.garmin_activity_id,
            athlete_id=body.athlete_id,
            athletes=roster,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "openai_error", "message": safe_error(exc)},
        ) from exc
    return ChatResponse(
        conversation_id=conversation.id,
        messages=[
            ChatMessageOut(id=item.id, role=item.role, content=item.content, created_at=item.created_at)
            for item in messages
        ],
    )
