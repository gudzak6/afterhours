"""Coach roster, athlete pages, and the daily briefing."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.routes import _athlete_out, _classification_map, apply_athlete_update
from app.config import Settings, get_settings
from app.database import get_db
from app.garmin.mapping import pace_seconds_per_mile
from app.models import (
    Activity,
    Athlete,
    AthleteThreshold,
    CoachingBrief,
    GarminConnection,
    PlanRevision,
    ScheduledWorkout,
    SyncJob,
    TrainingGoal,
    WorkoutAnalysis,
    WorkoutClassification,
)
from app.schemas import AthleteOut, AthleteUpdate
from app.services.adherence import (
    METERS_PER_MILE,
    format_pace,
    load_plan_view,
    normalize_workout_type,
    parse_pace,
    parse_plan_csv,
    parse_plan_xlsx,
    prescription_snapshot,
)
from app.coach.engine import present_report
from app.services.brief import brief_for_day, deliver_daily_brief, generate_brief
from app.services.efforts import running_stats, save_best_effort
from app.services.history import mileage_chart, weekly_mileage
from app.services.program import next_monday, workouts_from_program, workouts_from_request
from app.services.mailer import smtp_configured
from app.services.mileage import as_utc
from app.services.portal import goals_payload
from app.services.roster import attention_reasons, training_status
from app.services.athletes import delete_athlete
from app.services.sync import SyncInProgress, athletes_for_coach, ensure_coach, run_sync, sync_saved_athlete_keys

router = APIRouter()


class CoachOut(BaseModel):
    display_name: str
    email: str | None
    timezone: str
    email_notifications_enabled: bool
    email_configured: bool


class CoachUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    email_notifications_enabled: bool | None = None


class AthleteCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class PlanIn(BaseModel):
    scheduled_date: date
    title: str = Field(min_length=1, max_length=200)
    details: str | None = None
    workout_type: str | None = None
    distance_miles: float | None = None
    warmup: str | None = None
    cooldown: str | None = None
    repetitions: int | None = None
    rep_distance_miles: float | None = None
    recovery_seconds: float | None = None
    target_pace: str | None = None
    intensity: str | None = None
    coach_notes: str | None = None


class PlanImport(BaseModel):
    filename: str
    text: str | None = None
    content_base64: str | None = None


class ProgramImport(BaseModel):
    filename: str = "request.txt"
    text: str | None = None
    content_base64: str | None = None
    start_date: date | None = None
    request: str | None = None


class PlanMatch(BaseModel):
    garmin_activity_id: int | None = None
    confirmed_missed: bool = False


class RosterAthlete(BaseModel):
    id: int
    display_name: str
    race_goal: str | None
    target_time: str | None
    weekly_miles: float | None
    recent_activity: str | None
    recent_activity_id: int | None
    recent_activity_at: str | None
    training_status: str
    attention_reasons: list[str]
    garmin_status: str
    ran_today: bool
    planned_weekly_miles: float | None = None
    workouts_completed: int = 0
    workouts_scheduled: int = 0
    workouts_still_scheduled: int = 0
    key_workout_status: str | None = None


class DashboardOut(BaseModel):
    athlete_count: int
    ran_today: int
    attention_count: int
    athletes: list[RosterAthlete]
    recent_activities: list[dict]
    planned_workouts: list[dict]
    today: str
    week_start: str
    brief: dict | None
    brief_created_at: str | None
    coach: CoachOut


def _coach_payload(coach, settings: Settings) -> CoachOut:
    return CoachOut(
        display_name=coach.display_name,
        email=coach.email,
        timezone=coach.timezone,
        email_notifications_enabled=coach.email_notifications_enabled,
        email_configured=smtp_configured(settings),
    )


def _brief_plan(plan: ScheduledWorkout, *, include_date: bool) -> dict:
    summary = _planned_summary(plan, None)
    detail = summary["detail"]
    if detail:
        measured = [part for part in detail.split(" · ") if any(character.isdigit() for character in part)]
        detail = " · ".join(measured) or None
    shaped: dict = {"title": summary["title"], "detail": detail}
    prescription = " ".join((plan.details or "").split())
    if prescription:
        shaped["prescription"] = prescription[:500]
    if include_date:
        shaped["scheduled_date"] = plan.scheduled_date.isoformat()
    return shaped


def _plans_for_brief(db: Session, facts: list[dict], day: date) -> tuple[dict[int, list[dict]], dict[int, list[dict]]]:
    athlete_ids = [int(item["athlete_id"]) for item in facts] or [0]
    week_start = day - timedelta(days=(day.weekday() + 1) % 7)
    week_end = max(week_start + timedelta(days=7), day + timedelta(days=8))
    plans = list(
        db.scalars(
            select(ScheduledWorkout)
            .where(
                ScheduledWorkout.athlete_id.in_(athlete_ids),
                ScheduledWorkout.scheduled_date >= week_start,
                ScheduledWorkout.scheduled_date < week_end,
            )
            .order_by(ScheduledWorkout.scheduled_date, ScheduledWorkout.id)
        ).all()
    )
    on_day: dict[int, list[dict]] = {}
    surrounding: dict[int, list[dict]] = {}
    for plan in plans:
        target = on_day if plan.scheduled_date == day else surrounding
        target.setdefault(plan.athlete_id, []).append(_brief_plan(plan, include_date=plan.scheduled_date != day))
    return on_day, surrounding


def _planned_summary(plan: ScheduledWorkout, athlete_name: str | None) -> dict:
    bits: list[str] = []
    if plan.workout_type:
        bits.append(plan.workout_type.replace("_", " "))
    if plan.distance_meters:
        bits.append(f"{plan.distance_meters / METERS_PER_MILE:.2f} mi")
    if plan.repetitions:
        if plan.rep_distance_meters:
            bits.append(f"{plan.repetitions} x {plan.rep_distance_meters / METERS_PER_MILE:.2f} mi")
        else:
            bits.append(f"{plan.repetitions} reps")
    pace = format_pace(plan.target_pace_seconds_per_mile)
    if pace:
        bits.append(f"{pace}/mi")
    if plan.intensity:
        bits.append(plan.intensity)
    return {
        "id": plan.id,
        "athlete_id": plan.athlete_id,
        "athlete_name": athlete_name,
        "scheduled_date": plan.scheduled_date.isoformat(),
        "title": plan.title,
        "detail": " · ".join(bits) or None,
    }


def _classification_marks(db: Session, activities: list[Activity]) -> dict[int, dict]:
    activity_ids = [activity.id for activity in activities]
    if not activity_ids:
        return {}
    marks: dict[int, dict] = {}
    rows = db.scalars(select(WorkoutClassification).where(WorkoutClassification.activity_id.in_(activity_ids))).all()
    for row in rows:
        evidence = row.evidence if isinstance(row.evidence, dict) else {}
        intelligence = evidence.get("workout_intelligence") if isinstance(evidence, dict) else None
        repetitions = intelligence.get("repetitions") if isinstance(intelligence, dict) else None
        marks[row.activity_id] = {
            "workout_type": row.workout_type,
            "repetition_count": repetitions if isinstance(repetitions, int) else None,
        }
    return marks


def _analysis_summaries(db: Session, activities: list[Activity]) -> dict[int, dict]:
    activity_ids = [activity.id for activity in activities]
    if not activity_ids:
        return {}
    rows = db.scalars(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id.in_(activity_ids), WorkoutAnalysis.status == "ready")
        .order_by(WorkoutAnalysis.id.desc())
    ).all()
    stored: dict[int, dict] = {}
    for row in rows:
        if row.activity_id in stored or not isinstance(row.report, dict):
            continue
        stored[row.activity_id] = row.report
    types = {
        row.activity_id: row.workout_type
        for row in db.scalars(select(WorkoutClassification).where(WorkoutClassification.activity_id.in_(activity_ids))).all()
    }
    summaries: dict[int, dict] = {}
    for activity in activities:
        shown = present_report(
            stored.get(activity.id),
            workout_type=types.get(activity.id),
            distance_meters=activity.distance_meters,
            average_speed_mps=activity.average_speed_mps,
        )
        if shown is None:
            continue
        summary = shown.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries[activity.id] = {"summary": summary.strip(), "kind": shown.get("analysis_kind")}
    return summaries


def _owned(db: Session, settings: Settings, athlete_id: int) -> Athlete:
    coach = ensure_coach(db, settings)
    athlete = db.get(Athlete, athlete_id)
    if athlete is None or athlete.coach_id != coach.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Athlete not found"})
    return athlete


def _recent_runs(activities: list[Activity]) -> list[dict]:
    dated = [activity for activity in activities if activity.start_time_local and len(activity.start_time_local) >= 10]
    dated.sort(key=lambda activity: activity.start_time_local or "", reverse=True)
    runs = []
    for activity in dated[:16]:
        pace = pace_seconds_per_mile(activity.average_speed_mps)
        runs.append(
            {
                "date": activity.start_time_local[:10],
                "name": activity.name,
                "distance_miles": None if activity.distance_meters is None else round(activity.distance_meters / 1609.344, 2),
                "pace_seconds_per_mile": None if pace is None else round(pace),
                "average_heart_rate_bpm": activity.average_heart_rate_bpm,
                "garmin_activity_id": activity.garmin_activity_id,
            }
        )
    return runs


def _stored_analyses(db: Session, activities: list[Activity]) -> list[dict]:
    by_id = {activity.id: activity for activity in activities}
    if not by_id:
        return []
    rows = list(
        db.scalars(
            select(WorkoutAnalysis)
            .where(WorkoutAnalysis.activity_id.in_(by_id), WorkoutAnalysis.status == "ready")
            .order_by(WorkoutAnalysis.id.desc())
            .limit(8)
        ).all()
    )
    seen: set[int] = set()
    stored = []
    for row in rows:
        if row.activity_id in seen:
            continue
        seen.add(row.activity_id)
        activity = by_id[row.activity_id]
        report = row.report if isinstance(row.report, dict) else {}
        summary = report.get("summary") if isinstance(report.get("summary"), str) else None
        impact = report.get("training_impact") if isinstance(report.get("training_impact"), str) else None
        stored.append(
            {
                "activity_date": activity.start_time_local[:10] if activity.start_time_local else None,
                "garmin_activity_id": activity.garmin_activity_id,
                "effort_level": report.get("effort_level") if isinstance(report.get("effort_level"), str) else None,
                "summary": None if summary is None else summary[:500],
                "training_impact": None if impact is None else impact[:300],
            }
        )
        if len(stored) == 4:
            break
    return stored


def _saved_thresholds(db: Session, athlete_id: int) -> list[dict]:
    rows = db.scalars(select(AthleteThreshold).where(AthleteThreshold.athlete_id == athlete_id)).all()
    return [
        {
            "name": row.name,
            "pace_seconds_per_mile": row.pace_seconds_per_mile,
            "heart_rate_bpm": row.heart_rate_bpm,
        }
        for row in rows
    ]


def _roster(db: Session, settings: Settings) -> tuple[object, list[RosterAthlete], list[dict]]:
    coach = ensure_coach(db, settings)
    athletes = athletes_for_coach(db, coach)
    zone = ZoneInfo(coach.timezone or "America/New_York")
    today = datetime.now(zone).date()
    now = datetime.now(UTC)
    rows: list[RosterAthlete] = []
    facts: list[dict] = []
    for athlete in athletes:
        activities = list(
            db.scalars(
                select(Activity)
                .where(Activity.athlete_id == athlete.id)
                .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc())
            ).all()
        )
        goal = db.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
        connection = db.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
        activity_days = {
            activity.start_time_local[:10]
            for activity in activities
            if activity.start_time_local and len(activity.start_time_local) >= 10
        }
        plan_view = _plan_view(db, athlete.id, today)
        missed = sum(week["confirmed_missed"] for week in plan_view["weeks"])
        adherence_notes = [note["note"] for note in plan_view["adherence_notes"] if note["kind"] in {"shortfall", "missed", "partial"}]
        latest = next((activity for activity in activities if activity.start_time_utc is not None), None)
        analysis = None
        if latest is not None:
            analysis = db.scalar(
                select(WorkoutAnalysis)
                .where(WorkoutAnalysis.activity_id == latest.id, WorkoutAnalysis.status == "ready")
                .order_by(WorkoutAnalysis.id.desc())
            )
        report = {} if analysis is None or not isinstance(analysis.report, dict) else analysis.report
        effort = report.get("effort_level") if isinstance(report.get("effort_level"), str) else None
        goal_status = report.get("goal_progress_status") if isinstance(report.get("goal_progress_status"), str) else None
        reasons = attention_reasons(
            last_activity_at=None if latest is None else latest.start_time_utc,
            now=now,
            missed_planned_sessions=missed,
            latest_effort=effort,
            latest_goal_status=goal_status,
        )
        reasons.extend(note for note in adherence_notes if note not in reasons)
        status = training_status(reasons, has_activities=bool(activities), goal_status=goal_status)
        week = weekly_mileage(activities, now=now)
        current_week = None if not week else week[-1]["distance_miles"]
        ran_today = today.isoformat() in activity_days
        recent_label = None
        if latest is not None:
            miles = None if latest.distance_meters is None else round(latest.distance_meters / 1609.344, 2)
            recent_label = latest.name or latest.activity_type_key or "Activity"
            if miles is not None:
                recent_label = f"{recent_label} · {miles} mi"
        rows.append(
            RosterAthlete(
                id=athlete.id,
                display_name=athlete.display_name,
                race_goal=None if goal is None else goal.primary_race_goal,
                target_time=athlete.target_time,
                weekly_miles=current_week,
                recent_activity=recent_label,
                recent_activity_id=None if latest is None else latest.garmin_activity_id,
                recent_activity_at=None if latest is None else latest.start_time_local,
                training_status=status,
                attention_reasons=reasons,
                garmin_status="not_connected" if connection is None else connection.status,
                ran_today=ran_today,
                planned_weekly_miles=None if plan_view["current_week"] is None else plan_view["current_week"]["planned_miles"],
                workouts_completed=0 if plan_view["current_week"] is None else plan_view["current_week"]["completed_workouts"],
                workouts_scheduled=0 if plan_view["current_week"] is None else plan_view["current_week"]["planned_workouts"],
                workouts_still_scheduled=0 if plan_view["current_week"] is None else plan_view["current_week"]["still_scheduled"],
                key_workout_status=plan_view["key_workout_status"],
            )
        )
        positive = report.get("what_went_well") if isinstance(report.get("what_went_well"), list) else []
        facts.append(
            {
                "athlete_id": athlete.id,
                "athlete_name": athlete.display_name,
                "race_goal": None if goal is None else goal.primary_race_goal,
                "target_time": athlete.target_time,
                "ran_today": ran_today,
                "training_status": status,
                "attention_reasons": reasons,
                "weekly_miles": current_week,
                "weekly_miles_history": [
                    {
                        "week_start": item["week_start"],
                        "distance_miles": None if item["distance_miles"] is None else round(item["distance_miles"], 1),
                        "activity_count": item["activity_count"],
                    }
                    for item in (week or [])[-4:]
                ],
                "recent_activity": recent_label,
                "recent_runs": _recent_runs(activities),
                "garmin_activity_id": None if latest is None else latest.garmin_activity_id,
                "stored_effort": effort,
                "stored_goal_progress_status": goal_status,
                "stored_positive_notes": [item for item in positive if isinstance(item, str)][:2],
                "stored_summary": report.get("summary") if isinstance(report.get("summary"), str) else None,
                "stored_analyses": _stored_analyses(db, activities),
                "saved_thresholds": _saved_thresholds(db, athlete.id),
                "planned_weekly_miles": None if plan_view["current_week"] is None else plan_view["current_week"]["planned_miles"],
                "actual_weekly_miles": current_week,
                "workouts_completed": 0 if plan_view["current_week"] is None else plan_view["current_week"]["completed_workouts"],
                "workouts_scheduled": 0 if plan_view["current_week"] is None else plan_view["current_week"]["planned_workouts"],
                "key_workout_status": plan_view["key_workout_status"],
                "adherence_notes": plan_view["adherence_notes"],
                "data_not_stored": [
                    "resting_heart_rate",
                    "hrv",
                    "athlete_reported_fatigue",
                    "athlete_reported_soreness",
                ],
            }
        )
    return coach, rows, facts


@router.get("/api/coach", response_model=CoachOut)
def get_coach(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> CoachOut:
    return _coach_payload(ensure_coach(db, settings), settings)


@router.patch("/api/coach", response_model=CoachOut)
def update_coach(
    payload: CoachUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CoachOut:
    coach = ensure_coach(db, settings)
    changes = payload.model_dump(exclude_unset=True)
    if "timezone" in changes and changes["timezone"]:
        try:
            ZoneInfo(changes["timezone"])
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_timezone", "message": "Unrecognized timezone"}) from exc
    for field, value in changes.items():
        setattr(coach, field, value)
    coach.updated_at = datetime.now(UTC)
    db.commit()
    return _coach_payload(coach, settings)


@router.post("/api/coach/sync")
def sync_roster(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    """Pull the latest Garmin activities for the coach account and every signed-in athlete."""
    jobs = []
    if settings.garmin_key_configured:
        try:
            jobs.append(run_sync(db, settings, trigger="manual"))
        except SyncInProgress as exc:
            raise HTTPException(status_code=409, detail={"code": "sync_in_progress", "message": str(exc)}) from exc
    jobs.extend(sync_saved_athlete_keys(db, settings))
    return {
        "synced": len(jobs),
        "imported": sum(job.activities_imported for job in jobs),
        "updated": sum(job.activities_updated for job in jobs),
        "errors": [job.error_message for job in jobs if job.status != "succeeded" and job.error_message],
    }


@router.get("/api/coach/dashboard", response_model=DashboardOut)
def dashboard(
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DashboardOut:
    coach, rows, _facts = _roster(db, settings)
    zone = ZoneInfo(coach.timezone or "America/New_York")
    today = datetime.now(zone).date()
    selected = day or today
    brief = brief_for_day(db, coach, selected)
    week_start = selected - timedelta(days=(selected.weekday() + 1) % 7)
    monday = selected - timedelta(days=selected.weekday())
    range_start = min(week_start, monday)
    range_end = max(week_start + timedelta(days=7), monday + timedelta(days=7))
    recent = list(
        db.scalars(
            select(Activity)
            .where(
                Activity.athlete_id.in_([row.id for row in rows] or [0]),
                Activity.start_time_local >= range_start.isoformat(),
                Activity.start_time_local < range_end.isoformat(),
            )
            .order_by(Activity.start_time_local.desc())
        ).all()
    )
    names = {row.id: row.display_name for row in rows}
    summaries = _analysis_summaries(db, recent)
    structure = _classification_marks(db, recent)
    roster_ids = [row.id for row in rows] or [0]
    plans = list(
        db.scalars(
            select(ScheduledWorkout)
            .where(
                ScheduledWorkout.athlete_id.in_(roster_ids),
                ScheduledWorkout.scheduled_date >= range_start,
                ScheduledWorkout.scheduled_date < range_end,
            )
            .order_by(ScheduledWorkout.scheduled_date, ScheduledWorkout.id)
        ).all()
    )
    return DashboardOut(
        athlete_count=len(rows),
        ran_today=sum(1 for row in rows if row.ran_today),
        attention_count=sum(1 for row in rows if row.training_status == "attention"),
        athletes=rows,
        recent_activities=[
            {
                "garmin_activity_id": activity.garmin_activity_id,
                "athlete_id": activity.athlete_id,
                "athlete_name": names.get(activity.athlete_id),
                "name": activity.name,
                "distance_meters": activity.distance_meters,
                "duration_seconds": activity.duration_seconds,
                "average_pace_seconds_per_mile": pace_seconds_per_mile(activity.average_speed_mps),
                "location_name": activity.location_name,
                "start_time_local": activity.start_time_local,
                "analysis_summary": None if summaries.get(activity.id) is None else summaries[activity.id]["summary"],
                "analysis_kind": None if summaries.get(activity.id) is None else summaries[activity.id]["kind"],
                "workout_type": None if structure.get(activity.id) is None else structure[activity.id]["workout_type"],
                "repetition_count": None if structure.get(activity.id) is None else structure[activity.id]["repetition_count"],
            }
            for activity in recent
        ],
        planned_workouts=[_planned_summary(plan, names.get(plan.athlete_id)) for plan in plans],
        today=today.isoformat(),
        week_start=week_start.isoformat(),
        brief=None if brief is None else brief.report,
        brief_created_at=None if brief is None else brief.created_at.isoformat(),
        coach=_coach_payload(coach, settings),
    )


class BriefCreate(BaseModel):
    day: date | None = None


@router.post("/api/coach/brief")
def create_brief(
    payload: BriefCreate | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    coach, _rows, facts = _roster(db, settings)
    selected = None if payload is None else payload.day
    plans_by_athlete: dict[int, list[dict]] = {}
    surrounding_by_athlete: dict[int, list[dict]] = {}
    if selected is not None:
        plans_by_athlete, surrounding_by_athlete = _plans_for_brief(db, facts, selected)
    try:
        brief = generate_brief(
            db,
            settings,
            coach,
            facts,
            day=selected,
            plans_by_athlete=plans_by_athlete,
            surrounding_by_athlete=surrounding_by_athlete,
        )
    except RuntimeError as exc:
        code = str(exc).split(":", 1)[0]
        status = 503 if code == "gemini_not_configured" else 502
        raise HTTPException(status_code=status, detail={"code": code, "message": "The coaching brief was not stored."}) from exc
    return {"status": brief.status, "created_at": brief.created_at.isoformat(), "report": brief.report}


@router.post("/api/coach/athletes", response_model=AthleteOut)
def create_athlete(
    payload: AthleteCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AthleteOut:
    coach = ensure_coach(db, settings)
    now = datetime.now(UTC)
    athlete = Athlete(coach_id=coach.id, display_name=payload.display_name.strip(), created_at=now, updated_at=now)
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return _athlete_out(db, athlete, settings)


@router.get("/api/athletes/{athlete_id}", response_model=AthleteOut)
def get_athlete_profile(
    athlete_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AthleteOut:
    return _athlete_out(db, _owned(db, settings, athlete_id), settings)


@router.patch("/api/athletes/{athlete_id}", response_model=AthleteOut)
def update_athlete_profile(
    athlete_id: int,
    payload: AthleteUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AthleteOut:
    athlete = _owned(db, settings, athlete_id)
    return apply_athlete_update(db, settings, athlete, payload)


@router.delete("/api/athletes/{athlete_id}", status_code=204)
def remove_athlete(
    athlete_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    delete_athlete(db, _owned(db, settings, athlete_id))


def _status_card(db: Session, athlete: Athlete, activities: list[Activity], today: date, now: datetime) -> RosterAthlete:
    """Status for one athlete. The roster page builds the same card for everyone."""
    goal = db.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
    connection = db.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
    activity_days = {
        activity.start_time_local[:10]
        for activity in activities
        if activity.start_time_local and len(activity.start_time_local) >= 10
    }
    plan_view = _plan_view(db, athlete.id, today)
    missed = sum(week["confirmed_missed"] for week in plan_view["weeks"])
    adherence_notes = [note["note"] for note in plan_view["adherence_notes"] if note["kind"] in {"shortfall", "missed", "partial"}]
    latest = next((activity for activity in activities if activity.start_time_utc is not None), None)
    analysis = None
    if latest is not None:
        analysis = db.scalar(
            select(WorkoutAnalysis)
            .where(WorkoutAnalysis.activity_id == latest.id, WorkoutAnalysis.status == "ready")
            .order_by(WorkoutAnalysis.id.desc())
        )
    report = {} if analysis is None or not isinstance(analysis.report, dict) else analysis.report
    effort = report.get("effort_level") if isinstance(report.get("effort_level"), str) else None
    goal_status = report.get("goal_progress_status") if isinstance(report.get("goal_progress_status"), str) else None
    reasons = attention_reasons(
        last_activity_at=None if latest is None else latest.start_time_utc,
        now=now,
        missed_planned_sessions=missed,
        latest_effort=effort,
        latest_goal_status=goal_status,
    )
    reasons.extend(note for note in adherence_notes if note not in reasons)
    status = training_status(reasons, has_activities=bool(activities), goal_status=goal_status)
    week = weekly_mileage(activities, now=now)
    current_week = None if not week else week[-1]["distance_miles"]
    recent_label = None
    if latest is not None:
        miles = None if latest.distance_meters is None else round(latest.distance_meters / 1609.344, 2)
        recent_label = latest.name or latest.activity_type_key or "Activity"
        if miles is not None:
            recent_label = f"{recent_label} · {miles} mi"
    return RosterAthlete(
        id=athlete.id,
        display_name=athlete.display_name,
        race_goal=None if goal is None else goal.primary_race_goal,
        target_time=athlete.target_time,
        weekly_miles=current_week,
        recent_activity=recent_label,
        recent_activity_id=None if latest is None else latest.garmin_activity_id,
        recent_activity_at=None if latest is None else latest.start_time_local,
        training_status=status,
        attention_reasons=reasons,
        garmin_status="not_connected" if connection is None else connection.status,
        ran_today=today.isoformat() in activity_days,
        planned_weekly_miles=None if plan_view["current_week"] is None else plan_view["current_week"]["planned_miles"],
        workouts_completed=0 if plan_view["current_week"] is None else plan_view["current_week"]["completed_workouts"],
        workouts_scheduled=0 if plan_view["current_week"] is None else plan_view["current_week"]["planned_workouts"],
        workouts_still_scheduled=0 if plan_view["current_week"] is None else plan_view["current_week"]["still_scheduled"],
        key_workout_status=plan_view["key_workout_status"],
    )


@router.get("/api/athletes/{athlete_id}/overview")
def athlete_overview(
    athlete_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    coach = ensure_coach(db, settings)
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.athlete_id == athlete.id)
            .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc())
        ).all()
    )
    now = datetime.now(UTC)
    today = datetime.now(ZoneInfo(coach.timezone or "America/New_York")).date()
    card = _status_card(db, athlete, activities, today, now)
    recent = sorted(
        [activity for activity in activities if activity.start_time_utc is not None],
        key=lambda activity: as_utc(activity.start_time_utc),
        reverse=True,
    )[:6]
    classifications = _classification_map(db, [activity.id for activity in recent])
    goals = goals_payload(db, athlete)
    return {
        "athlete": _athlete_out(db, athlete, settings).model_dump(mode="json"),
        "status": card.model_dump(),
        "weekly_mileage": weekly_mileage(activities, now=now),
        "mileage_chart": mileage_chart(activities, today=today),
        "running_stats": running_stats(db, activities, today=today, athlete_id=athlete.id),
        "goal": {
            "primary_race_goal": goals["primary_race_goal"],
            "goal_race_date": goals["goal_race_date"],
            "target_time": goals["target_time"],
        },
        "races": goals["races"],
        "recent_workouts": [
            {
                "garmin_activity_id": activity.garmin_activity_id,
                "name": activity.name,
                "distance_meters": activity.distance_meters,
                "start_time_local": activity.start_time_local,
                "workout_type": None if classifications.get(activity.id) is None else classifications[activity.id].workout_type,
            }
            for activity in recent
        ],
    }


class BestEffortUpdate(BaseModel):
    label: str
    duration_seconds: float | None = None


@router.patch("/api/athletes/{athlete_id}/best-efforts")
def update_best_effort(
    athlete_id: int,
    payload: BestEffortUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    try:
        save_best_effort(db, athlete.id, payload.label.strip(), payload.duration_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    activities = list(db.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    coach = ensure_coach(db, settings)
    today = datetime.now(ZoneInfo(coach.timezone or "America/New_York")).date()
    return running_stats(db, activities, today=today, athlete_id=athlete.id)


def _plan_view(db: Session, athlete_id: int, today: date):
    last_sync = db.scalar(
        select(SyncJob)
        .where(SyncJob.athlete_id == athlete_id, SyncJob.status == "succeeded")
        .order_by(SyncJob.finished_at.desc())
    )
    return load_plan_view(
        db,
        athlete_id,
        today=today,
        last_sync_at=None if last_sync is None else last_sync.finished_at,
    )


def _apply_plan(row: ScheduledWorkout, payload: PlanIn) -> None:
    row.scheduled_date = payload.scheduled_date
    row.title = payload.title.strip()
    row.details = None if payload.details is None else payload.details.strip() or None
    row.workout_type = normalize_workout_type(payload.workout_type)
    row.distance_meters = None if payload.distance_miles is None else payload.distance_miles * METERS_PER_MILE
    row.warmup = None if payload.warmup is None else payload.warmup.strip() or None
    row.cooldown = None if payload.cooldown is None else payload.cooldown.strip() or None
    row.repetitions = payload.repetitions
    row.rep_distance_meters = None if payload.rep_distance_miles is None else payload.rep_distance_miles * METERS_PER_MILE
    row.recovery_seconds = payload.recovery_seconds
    row.target_pace_seconds_per_mile = parse_pace(payload.target_pace)
    row.intensity = None if payload.intensity is None else payload.intensity.strip() or None
    row.coach_notes = None if payload.coach_notes is None else payload.coach_notes.strip() or None
    row.updated_at = datetime.now(UTC)


@router.get("/api/athletes/{athlete_id}/plan")
def athlete_plan(
    athlete_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    coach = ensure_coach(db, settings)
    today = datetime.now(ZoneInfo(coach.timezone or "America/New_York")).date()
    view = _plan_view(db, athlete.id, today)
    return {"trend": view["trend"], "weeks": view["weeks"], "workouts": view["workouts"]}


@router.post("/api/athletes/{athlete_id}/plan")
def add_plan(
    athlete_id: int,
    payload: PlanIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    row = ScheduledWorkout(athlete_id=athlete.id, title=payload.title.strip(), scheduled_date=payload.scheduled_date, created_at=datetime.now(UTC))
    _apply_plan(row, payload)
    row.original_prescription = prescription_snapshot(row)
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.patch("/api/athletes/{athlete_id}/plan/{plan_id}")
def edit_plan(
    athlete_id: int,
    plan_id: int,
    payload: PlanIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    row = db.get(ScheduledWorkout, plan_id)
    if row is None or row.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Planned workout not found"})
    previous = prescription_snapshot(row)
    if row.original_prescription is None:
        row.original_prescription = previous
    db.add(PlanRevision(scheduled_workout_id=row.id, prescription=previous, created_at=datetime.now(UTC)))
    _apply_plan(row, payload)
    db.commit()
    return {"id": row.id}


@router.post("/api/athletes/{athlete_id}/plan/import")
def import_plan(
    athlete_id: int,
    payload: PlanImport,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    import base64

    athlete = _owned(db, settings, athlete_id)
    name = payload.filename.lower()
    if name.endswith(".xlsx") and payload.content_base64:
        plans, errors = parse_plan_xlsx(base64.b64decode(payload.content_base64))
    elif payload.text:
        plans, errors = parse_plan_csv(payload.text)
    else:
        raise HTTPException(status_code=422, detail={"code": "unreadable_plan", "message": "Upload a CSV or Excel file."})
    created = 0
    for item in plans:
        row = ScheduledWorkout(athlete_id=athlete.id, title=item["title"], scheduled_date=item["scheduled_date"], created_at=datetime.now(UTC))
        for field, value in item.items():
            setattr(row, field, value)
        row.original_prescription = prescription_snapshot(row)
        row.updated_at = row.created_at
        db.add(row)
        created += 1
    db.commit()
    return {"created": created, "errors": errors}


@router.post("/api/athletes/{athlete_id}/plan/program")
def import_program(
    athlete_id: int,
    payload: ProgramImport,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    coach = ensure_coach(db, settings)
    today = datetime.now(ZoneInfo(coach.timezone or "America/New_York")).date()
    start = payload.start_date or next_monday(today)
    asked = (payload.request or "").strip()
    try:
        if asked:
            goal = db.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
            plans, notes, source = workouts_from_request(
                settings,
                asked,
                today=today,
                start=start,
                athlete_name=athlete.display_name,
                race_goal=None if goal is None else goal.primary_race_goal,
                target_time=athlete.target_time,
            )
        else:
            plans, notes, source = workouts_from_program(
                settings,
                payload.filename,
                payload.text,
                payload.content_base64,
                today=today,
                start=start,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "unreadable_plan", "message": str(exc)}) from exc
    except RuntimeError as exc:
        code = str(exc).split(":", 1)[0]
        status = 503 if code == "gemini_not_configured" else 502
        raise HTTPException(status_code=status, detail={"code": code, "message": "The program was not read."}) from exc
    except Exception as exc:
        from app.coach.engine import safe_error

        raise HTTPException(status_code=502, detail={"code": "gemini_error", "message": safe_error(exc)}) from exc
    if not plans:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "empty_program",
                "message": "No workouts were written from that request." if asked else "No dated workouts were found in that file.",
                "notes": notes,
            },
        )
    first = min(item["scheduled_date"] for item in plans)
    last = max(item["scheduled_date"] for item in plans)
    existing = list(
        db.scalars(
            select(ScheduledWorkout).where(
                ScheduledWorkout.athlete_id == athlete.id,
                ScheduledWorkout.scheduled_date >= first,
                ScheduledWorkout.scheduled_date <= last,
            )
        ).all()
    )
    replaced_ids = [row.id for row in existing]
    if replaced_ids:
        db.execute(delete(PlanRevision).where(PlanRevision.scheduled_workout_id.in_(replaced_ids)))
    for row in existing:
        db.delete(row)
    if existing:
        db.flush()
    for item in plans:
        row = ScheduledWorkout(
            athlete_id=athlete.id,
            title=item["title"],
            scheduled_date=item["scheduled_date"],
            created_at=datetime.now(UTC),
        )
        for field, value in item.items():
            setattr(row, field, value)
        row.original_prescription = prescription_snapshot(row)
        row.updated_at = row.created_at
        db.add(row)
    db.commit()
    return {
        "created": len(plans),
        "replaced": len(existing),
        "source": source,
        "start": first.isoformat(),
        "end": last.isoformat(),
        "notes": notes,
        "workouts": [
            {"scheduled_date": item["scheduled_date"].isoformat(), "title": item["title"]}
            for item in plans
        ],
    }


@router.patch("/api/athletes/{athlete_id}/plan/{plan_id}/match")
def match_plan(
    athlete_id: int,
    plan_id: int,
    payload: PlanMatch,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _owned(db, settings, athlete_id)
    row = db.get(ScheduledWorkout, plan_id)
    if row is None or row.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Planned workout not found"})
    if payload.confirmed_missed:
        row.match_activity_id = None
        row.match_source = "confirmed_missed"
    elif payload.garmin_activity_id is None:
        row.match_activity_id = None
        row.match_source = None
    else:
        activity = db.scalar(
            select(Activity).where(Activity.athlete_id == athlete.id, Activity.garmin_activity_id == payload.garmin_activity_id)
        )
        if activity is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Activity not found for this athlete"})
        row.match_activity_id = activity.id
        row.match_source = "manual"
    row.updated_at = datetime.now(UTC)
    db.commit()
    return {"id": row.id}


@router.delete("/api/athletes/{athlete_id}/plan/{plan_id}", status_code=204)
def delete_plan(
    athlete_id: int,
    plan_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    athlete = _owned(db, settings, athlete_id)
    row = db.get(ScheduledWorkout, plan_id)
    if row is None or row.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Planned workout not found"})
    db.delete(row)
    db.commit()


def run_notification_job() -> None:
    from app.database import SessionLocal

    settings = get_settings()
    session = SessionLocal()
    try:
        coach, _rows, facts = _roster(session, settings)
        try:
            deliver_daily_brief(session, settings, coach, facts)
        except Exception:
            session.rollback()
    finally:
        session.close()
