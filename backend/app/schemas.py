"""API response models. Numeric fields stay null when Garmin did not send them."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.garmin.mapping import METERS_PER_MILE, pace_seconds_per_mile
from app.models import Activity, SyncJob


class SyncRequest(BaseModel):
    lookback_days: int | None = Field(default=None, ge=0, le=3650)
    activity_type: str | None = Field(default=None, max_length=80)


class SyncJobOut(BaseModel):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    lookback_days: int | None
    activities_seen: int
    activities_imported: int
    activities_updated: int
    activities_skipped: int
    error_code: str | None
    error_message: str | None
    http_status: int | None

    @classmethod
    def from_job(cls, job: SyncJob) -> SyncJobOut:
        return cls(
            id=job.id,
            trigger=job.trigger,
            status=job.status,
            started_at=job.started_at,
            finished_at=job.finished_at,
            lookback_days=job.lookback_days,
            activities_seen=job.activities_seen,
            activities_imported=job.activities_imported,
            activities_updated=job.activities_updated,
            activities_skipped=job.activities_skipped,
            error_code=job.error_code,
            error_message=job.error_message,
            http_status=job.http_status,
        )


class ActivityOut(BaseModel):
    id: int
    garmin_activity_id: int
    name: str | None
    activity_type_key: str | None
    start_time_local: str | None
    start_time_gmt: str | None
    start_time_utc: datetime | None
    distance_meters: float | None
    distance_miles: float | None
    duration_seconds: float | None
    moving_duration_seconds: float | None
    elapsed_duration_raw: float | None
    average_speed_mps: float | None
    average_pace_seconds_per_mile: float | None
    average_heart_rate_bpm: float | None
    max_heart_rate_bpm: float | None
    elevation_gain_meters: float | None
    elevation_loss_meters: float | None
    average_cadence_spm: float | None
    calories: float | None
    lap_count: int | None
    location_name: str | None
    manual_activity: bool | None
    import_status: str
    analysis_status: str
    workout_type: str | None = None
    classification_source: str | None = None
    present_fields: list[str]
    start_latitude: float | None = None
    start_longitude: float | None = None
    athlete_id: int | None = None
    athlete_name: str | None = None

    @classmethod
    def from_activity(
        cls,
        activity: Activity,
        *,
        include_location: bool,
        workout_type: str | None = None,
        classification_source: str | None = None,
        analysis_status: str = "not_started",
        athlete_name: str | None = None,
    ) -> ActivityOut:
        distance_miles = None
        if activity.distance_meters is not None:
            distance_miles = activity.distance_meters / METERS_PER_MILE
        return cls(
            id=activity.id,
            garmin_activity_id=activity.garmin_activity_id,
            name=activity.name,
            activity_type_key=activity.activity_type_key,
            start_time_local=activity.start_time_local,
            start_time_gmt=activity.start_time_gmt,
            start_time_utc=activity.start_time_utc,
            distance_meters=activity.distance_meters,
            distance_miles=distance_miles,
            duration_seconds=activity.duration_seconds,
            moving_duration_seconds=activity.moving_duration_seconds,
            elapsed_duration_raw=activity.elapsed_duration_raw,
            average_speed_mps=activity.average_speed_mps,
            average_pace_seconds_per_mile=pace_seconds_per_mile(activity.average_speed_mps),
            average_heart_rate_bpm=activity.average_heart_rate_bpm,
            max_heart_rate_bpm=activity.max_heart_rate_bpm,
            elevation_gain_meters=activity.elevation_gain_meters,
            elevation_loss_meters=activity.elevation_loss_meters,
            average_cadence_spm=activity.average_cadence_spm,
            calories=activity.calories,
            lap_count=activity.lap_count,
            location_name=activity.location_name,
            manual_activity=activity.manual_activity,
            import_status=activity.import_status,
            analysis_status=analysis_status,
            workout_type=workout_type,
            classification_source=classification_source,
            present_fields=list(activity.present_fields or []),
            start_latitude=activity.start_latitude if include_location else None,
            start_longitude=activity.start_longitude if include_location else None,
            athlete_id=activity.athlete_id,
            athlete_name=athlete_name,
        )


class ActivityListOut(BaseModel):
    activities: list[ActivityOut]
    total: int


class TrainingWindow(BaseModel):
    days: int
    activity_count: int
    activities_with_distance: int
    distance_meters: float | None
    distance_miles: float | None


class WeeklyMileage(BaseModel):
    week_start: str
    activity_count: int
    distance_meters: float | None
    distance_miles: float | None


class TrainingSummaryOut(BaseModel):
    activity_count: int
    last_7_days: TrainingWindow
    last_28_days: TrainingWindow
    workout_counts: dict[str, int] = Field(default_factory=dict)
    hard_workouts_28_days: int = 0
    active_days_28: int = 0
    weekly_mileage: list[WeeklyMileage] = Field(default_factory=list)


class ThresholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    pace_seconds_per_mile: float | None = None
    heart_rate_bpm: float | None = None


class RecentRace(BaseModel):
    event: str | None = Field(default=None, max_length=200)
    race_date: date | None = None
    goal_time: str | None = Field(default=None, max_length=40)
    result_time: str | None = Field(default=None, max_length=40)


class AthleteIntake(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    events: str | None = Field(default=None, max_length=4000)
    outcome_goals: str | None = Field(default=None, max_length=4000)
    process_goals: str | None = Field(default=None, max_length=4000)
    personal_bests: str | None = Field(default=None, max_length=4000)
    weekly_miles_last_3_weeks: str | None = Field(default=None, max_length=80)
    weekly_miles_last_3_months: str | None = Field(default=None, max_length=80)
    training_stipulations: str | None = Field(default=None, max_length=4000)
    training_style: str | None = Field(default=None, max_length=4000)
    strengths: str | None = Field(default=None, max_length=4000)
    weaknesses: str | None = Field(default=None, max_length=4000)
    why_run: str | None = Field(default=None, max_length=4000)
    preferred_coach: str | None = Field(default=None, max_length=200)
    anything_else: str | None = Field(default=None, max_length=4000)
    heard_about_us: str | None = Field(default=None, max_length=4000)
    recent_races: list[RecentRace] = Field(default_factory=list, max_length=20)


def _blank(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def stored_intake(intake: AthleteIntake) -> dict | None:
    """JSON-safe intake. Empty answers are omitted so a blank form stores nothing."""
    raw = intake.model_dump(mode="json")
    races: list[dict] = []
    for race in raw.get("recent_races") or []:
        cleaned = {
            "event": _blank(race.get("event")),
            "race_date": race.get("race_date") or None,
            "goal_time": _blank(race.get("goal_time")),
            "result_time": _blank(race.get("result_time")),
        }
        if any(cleaned.values()):
            races.append(cleaned)
    payload = {
        key: _blank(value) if isinstance(value, str) else value
        for key, value in raw.items()
        if key != "recent_races"
    }
    payload["recent_races"] = races
    if not races and all(value in (None, "") for key, value in payload.items() if key != "recent_races"):
        return None
    return payload


class AthleteUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    running_experience: str | None = Field(default=None, max_length=80)
    typical_weekly_mileage: float | None = None
    max_heart_rate_bpm: float | None = None
    preferred_training_days: list[str] | None = None
    pace_zones: list[dict] | None = None
    heart_rate_zones: list[dict] | None = None
    primary_race_goal: str | None = Field(default=None, max_length=200)
    goal_race_date: date | None = None
    target_time: str | None = Field(default=None, max_length=40)
    coach_notes: str | None = None
    thresholds: list[ThresholdIn] | None = None
    intake: AthleteIntake | None = None


class ThresholdOut(BaseModel):
    name: str
    pace_seconds_per_mile: float | None
    heart_rate_bpm: float | None
    source: str


class AthleteOut(BaseModel):
    id: int
    display_name: str
    running_experience: str | None
    typical_weekly_mileage: float | None
    max_heart_rate_bpm: float | None
    preferred_training_days: list[str] | None = None
    pace_zones: list[dict] = Field(default_factory=list)
    heart_rate_zones: list[dict] = Field(default_factory=list)
    primary_race_goal: str | None = None
    goal_race_date: date | None = None
    target_time: str | None = None
    coach_notes: str | None = None
    intake: AthleteIntake = Field(default_factory=AthleteIntake)
    thresholds: list[ThresholdOut] = Field(default_factory=list)
    openai_configured: bool = False


class GarminStatusOut(BaseModel):
    configured: bool
    connection_status: str
    token_cached: bool
    token_expires_at: datetime | None
    last_error: str | None
    scheduler_enabled: bool
    scheduler_interval_minutes: int
    fit_download_documented: bool
    fit_download_implemented: bool
    fit_download_note: str
    last_sync: SyncJobOut | None


class LapOut(BaseModel):
    lap_number: int
    distance_meters: float | None
    distance_miles: float | None
    duration_seconds: float | None
    pace_seconds_per_mile: float | None
    average_speed_mps: float | None
    average_heart_rate_bpm: float | None
    max_heart_rate_bpm: float | None
    average_cadence: float | None
    cadence_field: str | None
    intensity: str | None
    lap_trigger: str | None
    present_fields: list[str]


class SegmentOut(BaseModel):
    segment_index: int
    kind: str
    start_lap: int | None
    end_lap: int | None
    lap_numbers: list[int]
    confidence: float | None
    source: str


class SeriesPoint(BaseModel):
    elapsed_seconds: float | None
    distance_meters: float | None
    pace_seconds_per_mile: float | None
    heart_rate_bpm: float | None
    altitude_meters: float | None
    cadence: float | None


class ClassificationOut(BaseModel):
    workout_type: str
    confidence: float | None
    source: str
    uncertainty: str | None
    evidence: dict


class ClassificationUpdate(BaseModel):
    workout_type: str = Field(min_length=1, max_length=40)


class ActivityDetailOut(BaseModel):
    activity: ActivityOut
    laps: list[LapOut]
    segments: list[SegmentOut]
    classification: ClassificationOut | None
    metrics: dict
    series: list[SeriesPoint]
    report: dict | None
    report_status: str
    fit_summary: dict | None
    workout_steps_found: bool


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    garmin_activity_id: int | None = None
    athlete_id: int | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: int
    messages: list[ChatMessageOut]


class FileImportStatus(BaseModel):
    running: bool
    counts: dict[str, int]
