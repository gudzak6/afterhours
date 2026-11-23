"""Athlete-facing training: the same plans and activities, from the athlete's side."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.routes import apply_athlete_update
from app.config import Settings
from app.garmin.mapping import METERS_PER_MILE, pace_seconds_per_mile
from app.models import (
    Activity,
    Athlete,
    AthleteThreshold,
    CoachMessage,
    GarminConnection,
    LactateReading,
    PlanRevision,
    Race,
    ScheduledWorkout,
    SyncJob,
    TrainingGoal,
    WorkoutClassification,
    WorkoutComment,
    WorkoutFeedback,
)
from app.schemas import AthleteIntake, AthleteUpdate
from app.services.adherence import _local_day, load_plan_view, prescription_snapshot
from app.services.efforts import running_stats
from app.services.history import weekly_mileage
from app.services.sync import ensure_coach

REQUIRED_INTAKE = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "events",
    "outcome_goals",
    "process_goals",
    "personal_bests",
    "weekly_miles_last_3_weeks",
    "weekly_miles_last_3_months",
    "training_stipulations",
    "training_style",
    "strengths",
    "weaknesses",
    "why_run",
    "preferred_coach",
)

INTAKE_LABELS = {
    "first_name": "First name",
    "last_name": "Last name",
    "email": "Email",
    "phone": "Phone",
    "events": "Events",
    "outcome_goals": "Outcome goals",
    "process_goals": "Process goals",
    "personal_bests": "Personal bests",
    "weekly_miles_last_3_weeks": "Miles over the last three weeks",
    "weekly_miles_last_3_months": "Miles over the last three months",
    "training_stipulations": "Training stipulations",
    "training_style": "Training that clicks",
    "strengths": "Strengths",
    "weaknesses": "Weaknesses",
    "why_run": "Why you run",
    "preferred_coach": "Preferred coach",
}

DISTANCES = (
    ("half marathon", 21097.5),
    ("half-marathon", 21097.5),
    ("marathon", 42195.0),
    ("10 mile", 16093.44),
    ("10-mile", 16093.44),
    ("50k", 50000.0),
    ("15k", 15000.0),
    ("10k", 10000.0),
    ("5k", 5000.0),
    ("1 mile", 1609.344),
    ("mile", 1609.344),
    ("800m", 800.0),
    ("400m", 400.0),
)

PREDICTIONS = (
    ("5K", 5000.0),
    ("10K", 10000.0),
    ("Half marathon", 21097.5),
    ("Marathon", 42195.0),
)

EASY_TYPES = {"easy", "recovery"}
QUALITY_TYPES = {"intervals", "threshold", "tempo", "marathon_pace", "strides"}


class PortalInputError(ValueError):
    def __init__(self, message: str, code: str = "invalid_intake") -> None:
        super().__init__(message)
        self.code = code


def coach_today(session: Session, settings: Settings) -> date:
    coach = ensure_coach(session, settings)
    try:
        zone = ZoneInfo(coach.timezone or "America/New_York")
    except Exception:
        zone = ZoneInfo("America/New_York")
    return datetime.now(zone).date()


def missing_intake_fields(intake: AthleteIntake) -> list[str]:
    payload = intake.model_dump()
    missing = []
    for key in REQUIRED_INTAKE:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(INTAKE_LABELS[key])
    email = (intake.email or "").strip()
    if email and "@" not in email:
        missing.append("A valid email")
    return missing


def intake_complete(raw: dict | None) -> bool:
    if not isinstance(raw, dict):
        return False
    for key in REQUIRED_INTAKE:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def find_athlete_by_email(session: Session, coach_id: int, email: str) -> Athlete | None:
    target = email.strip().lower()
    athletes = session.scalars(select(Athlete).where(Athlete.coach_id == coach_id)).all()
    for athlete in athletes:
        stored = (athlete.intake or {}).get("email") if isinstance(athlete.intake, dict) else None
        if isinstance(stored, str) and stored.strip().lower() == target:
            return athlete
    return None


def join_athlete(session: Session, settings: Settings, intake: AthleteIntake, athlete_id: int | None = None) -> Athlete:
    missing = missing_intake_fields(intake)
    if missing:
        raise PortalInputError("Fill in " + ", ".join(missing) + ".")
    coach = ensure_coach(session, settings)
    athlete = None
    if athlete_id is not None:
        existing = session.get(Athlete, athlete_id)
        if existing is not None and existing.coach_id == coach.id:
            athlete = existing
    if athlete is None:
        athlete = find_athlete_by_email(session, coach.id, intake.email or "")
    if athlete is None:
        now = datetime.now(UTC)
        athlete = Athlete(coach_id=coach.id, display_name="Athlete", created_at=now, updated_at=now)
        session.add(athlete)
        session.commit()
        session.refresh(athlete)
    apply_athlete_update(session, settings, athlete, AthleteUpdate(intake=intake))
    session.refresh(athlete)
    return athlete


def garmin_state(session: Session, athlete_id: int) -> dict:
    connection = session.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete_id))
    last = session.scalar(
        select(SyncJob)
        .where(SyncJob.athlete_id == athlete_id)
        .order_by(SyncJob.id.desc())
        .limit(1)
    )
    status = "not_connected" if connection is None else connection.status
    signed_in = bool(connection and ((connection.connect_token or "").strip() or (connection.personal_api_key or "").strip()))
    return {
        "connected": signed_in and status == "connected",
        "status": status,
        "key_saved": signed_in,
        "last_error": None if connection is None else connection.last_error,
        "last_sync_at": None if last is None or last.finished_at is None else last.finished_at.isoformat(),
    }


def save_garmin_login(session: Session, athlete: Athlete, email: str, password: str, mfa_code: str | None) -> str:
    """Sign in with Garmin Connect. The password is not written to the database."""
    from app.garmin.connect import GarminMfaRequired, GarminSignInError, sign_in_garmin

    try:
        token = sign_in_garmin(athlete.id, email, password, mfa_code)
    except GarminMfaRequired:
        raise
    except GarminSignInError as exc:
        raise PortalInputError(str(exc), code="garmin_sign_in") from exc
    now = datetime.now(UTC)
    connection = session.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
    if connection is None:
        connection = GarminConnection(athlete_id=athlete.id, status="pending", updated_at=now)
        session.add(connection)
    connection.garmin_email = email.strip()
    connection.connect_token = token
    connection.personal_api_key = None
    connection.status = "pending"
    connection.last_error = None
    connection.updated_at = now
    session.commit()
    if connection.connect_token == password:
        connection.connect_token = None
        session.commit()
        raise PortalInputError("Garmin sign-in was not stored safely.", code="garmin_sign_in")
    return token


def save_garmin_key(session: Session, athlete: Athlete, api_key: str) -> str:
    key = api_key.strip()
    if len(key) < 20:
        raise PortalInputError("Paste the Personal API key from Garmin Connect.")
    now = datetime.now(UTC)
    connection = session.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
    if connection is None:
        connection = GarminConnection(athlete_id=athlete.id, status="pending", updated_at=now)
        session.add(connection)
    connection.personal_api_key = key
    connection.status = "pending"
    connection.last_error = None
    connection.updated_at = now
    session.commit()
    return key


def _plan(session: Session, athlete_id: int, today: date) -> dict:
    last = session.scalar(
        select(SyncJob)
        .where(SyncJob.athlete_id == athlete_id, SyncJob.status == "succeeded")
        .order_by(SyncJob.id.desc())
        .limit(1)
    )
    finished = None if last is None else last.finished_at
    return load_plan_view(session, athlete_id, today=today, last_sync_at=finished)


def _activity_summary(activity: Activity) -> dict:
    notes = None
    overrides = activity.athlete_overrides or {}
    if isinstance(overrides, dict):
        notes = overrides.get("notes")
    miles = None if activity.distance_meters is None else activity.distance_meters / METERS_PER_MILE
    pace = pace_seconds_per_mile(activity.average_speed_mps)
    return {
        "garmin_activity_id": activity.garmin_activity_id,
        "name": activity.name,
        "start_time_local": activity.start_time_local,
        "distance_miles": miles,
        "duration_seconds": activity.duration_seconds,
        "pace_seconds_per_mile": pace,
        "average_heart_rate_bpm": activity.average_heart_rate_bpm,
        "manual": bool(activity.manual_activity) or activity.garmin_activity_id < 0,
        "notes": notes if isinstance(notes, str) else None,
    }


def recent_runs(session: Session, athlete_id: int, limit: int = 20) -> list[dict]:
    rows = session.scalars(
        select(Activity)
        .where(Activity.athlete_id == athlete_id)
        .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc(), Activity.id.desc())
        .limit(limit)
    ).all()
    return [_activity_summary(row) for row in rows]


def home(session: Session, settings: Settings, athlete: Athlete) -> dict:
    today = coach_today(session, settings)
    view = _plan(session, athlete.id, today)
    activities = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    today_runs = [_activity_summary(activity) for activity in activities if _local_day(activity) == today]
    today_workouts = [item for item in view["workouts"] if item["scheduled_date"] == today.isoformat()]
    upcoming = [item for item in view["workouts"] if item["scheduled_date"] > today.isoformat()][:6]
    first = ""
    if isinstance(athlete.intake, dict):
        first = str(athlete.intake.get("first_name") or "").strip()
    goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
    return {
        "today": today.isoformat(),
        "name": first or athlete.display_name,
        "workouts": today_workouts,
        "activities": today_runs,
        "recent": recent_runs(session, athlete.id, 5),
        "week": view.get("current_week"),
        "upcoming": upcoming,
        "goal": {
            "primary_race_goal": None if goal is None else goal.primary_race_goal,
            "goal_race_date": None if goal is None or goal.goal_race_date is None else goal.goal_race_date.isoformat(),
            "target_time": athlete.target_time,
        },
        "garmin": garmin_state(session, athlete.id),
    }


def calendar_month(session: Session, settings: Settings, athlete: Athlete, month: str) -> dict:
    try:
        year_text, month_text = month.split("-")
        year, month_number = int(year_text), int(month_text)
        if not 1 <= month_number <= 12:
            raise ValueError
    except ValueError as exc:
        raise PortalInputError("Choose a month as YYYY-MM.") from exc
    today = coach_today(session, settings)
    view = _plan(session, athlete.id, today)
    activities = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    by_workout: dict[str, list] = {}
    for workout in view["workouts"]:
        by_workout.setdefault(workout["scheduled_date"], []).append(
            {
                "id": workout["id"],
                "title": workout["title"],
                "details": workout["details"],
                "workout_type": workout["workout_type"],
                "status": workout["status"],
            }
        )
    by_run: dict[str, list] = {}
    for activity in activities:
        day = _local_day(activity)
        if day is None:
            continue
        by_run.setdefault(day.isoformat(), []).append(_activity_summary(activity))
    first = date(year, month_number, 1)
    start = first - timedelta(days=first.weekday())
    last = date(year, month_number, calendar.monthrange(year, month_number)[1])
    end = last + timedelta(days=(6 - last.weekday()) % 7)
    days = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        days.append(
            {
                "date": key,
                "in_month": cursor.month == month_number,
                "workouts": by_workout.get(key, []),
                "activities": by_run.get(key, []),
            }
        )
        cursor += timedelta(days=1)
    return {"month": f"{year:04d}-{month_number:02d}", "today": today.isoformat(), "days": days}


def week_view(session: Session, settings: Settings, athlete: Athlete) -> dict:
    today = coach_today(session, settings)
    view = _plan(session, athlete.id, today)
    view["today"] = today.isoformat()
    return view


def _short_day(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}"


def reschedule_workouts(session: Session, athlete: Athlete, moves: list[tuple[int, date]]) -> dict:
    """Move workouts onto new days and tell the coach in the message thread."""
    if not moves:
        raise PortalInputError("Move a workout before saving.")
    changes: list[str] = []
    for plan_id, new_day in moves:
        row = session.get(ScheduledWorkout, plan_id)
        if row is None or row.athlete_id != athlete.id:
            raise PortalInputError("That workout is not on your plan.")
        if row.scheduled_date == new_day:
            continue
        previous = prescription_snapshot(row)
        if row.original_prescription is None:
            row.original_prescription = previous
        session.add(PlanRevision(scheduled_workout_id=row.id, prescription=previous, created_at=datetime.now(UTC)))
        changes.append(f"{row.title}: {_short_day(row.scheduled_date)} to {_short_day(new_day)}")
        row.scheduled_date = new_day
        row.updated_at = datetime.now(UTC)
    if not changes:
        raise PortalInputError("Those workouts are already on those days.")
    name = athlete.display_name.strip() or "Athlete"
    session.add(
        CoachMessage(
            athlete_id=athlete.id,
            author="athlete",
            body=f"Schedule change from {name}\n" + "\n".join(changes),
            created_at=datetime.now(UTC),
        )
    )
    session.commit()
    return {"updated": len(changes)}


def workout_detail(session: Session, settings: Settings, athlete: Athlete, plan_id: int) -> dict | None:
    today = coach_today(session, settings)
    view = _plan(session, athlete.id, today)
    workout = next((item for item in view["workouts"] if item["id"] == plan_id), None)
    if workout is None:
        return None
    workout["feedback"] = _feedback_payload(
        session,
        athlete.id,
        scheduled_workout_id=plan_id,
        activity_garmin_id=None if workout["match"] is None else workout["match"]["garmin_activity_id"],
    )
    workout["comments"] = _comments(session, athlete.id, scheduled_workout_id=plan_id)
    return workout


def _comments(session: Session, athlete_id: int, *, scheduled_workout_id: int | None = None, activity_id: int | None = None) -> list[dict]:
    query = select(WorkoutComment).where(WorkoutComment.athlete_id == athlete_id)
    if scheduled_workout_id is not None:
        query = query.where(WorkoutComment.scheduled_workout_id == scheduled_workout_id)
    if activity_id is not None:
        query = query.where(WorkoutComment.activity_id == activity_id)
    rows = session.scalars(query.order_by(WorkoutComment.id)).all()
    return [
        {
            "id": row.id,
            "author": row.author,
            "body": row.body,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _feedback_payload(
    session: Session,
    athlete_id: int,
    *,
    scheduled_workout_id: int | None,
    activity_garmin_id: int | None,
) -> dict | None:
    activity_id = None
    if activity_garmin_id is not None:
        activity = session.scalar(
            select(Activity).where(
                Activity.athlete_id == athlete_id,
                Activity.garmin_activity_id == activity_garmin_id,
            )
        )
        activity_id = None if activity is None else activity.id
    row = None
    if activity_id is not None:
        row = session.scalar(
            select(WorkoutFeedback)
            .where(WorkoutFeedback.athlete_id == athlete_id, WorkoutFeedback.activity_id == activity_id)
            .order_by(WorkoutFeedback.id.desc())
        )
    if row is None and scheduled_workout_id is not None:
        row = session.scalar(
            select(WorkoutFeedback)
            .where(
                WorkoutFeedback.athlete_id == athlete_id,
                WorkoutFeedback.scheduled_workout_id == scheduled_workout_id,
            )
            .order_by(WorkoutFeedback.id.desc())
        )
    if row is None:
        return None
    return {
        "rpe": row.rpe,
        "fatigue": row.fatigue,
        "soreness": row.soreness,
        "comment": row.comment,
    }


def save_feedback(
    session: Session,
    athlete: Athlete,
    *,
    scheduled_workout_id: int | None,
    garmin_activity_id: int | None,
    rpe: int | None,
    fatigue: int | None,
    soreness: int | None,
    comment: str | None,
) -> dict:
    for label, value, limit in (("RPE", rpe, 10), ("Fatigue", fatigue, 5), ("Soreness", soreness, 5)):
        if value is not None and not 1 <= value <= limit:
            raise PortalInputError(f"{label} must be from 1 to {limit}.")
    activity = None
    if garmin_activity_id is not None:
        activity = _owned_activity(session, athlete, garmin_activity_id)
    if scheduled_workout_id is not None:
        plan = session.get(ScheduledWorkout, scheduled_workout_id)
        if plan is None or plan.athlete_id != athlete.id:
            raise PortalInputError("That workout is not on your plan.")
    if activity is None and scheduled_workout_id is None:
        raise PortalInputError("Choose a workout or a logged run.")
    row = None
    if activity is not None:
        row = session.scalar(select(WorkoutFeedback).where(WorkoutFeedback.activity_id == activity.id))
    if row is None and scheduled_workout_id is not None:
        row = session.scalar(
            select(WorkoutFeedback).where(WorkoutFeedback.scheduled_workout_id == scheduled_workout_id)
        )
    now = datetime.now(UTC)
    if row is None:
        row = WorkoutFeedback(
            athlete_id=athlete.id,
            activity_id=None if activity is None else activity.id,
            scheduled_workout_id=scheduled_workout_id,
            updated_at=now,
        )
        session.add(row)
    row.rpe = rpe
    row.fatigue = fatigue
    row.soreness = soreness
    row.comment = (comment or "").strip() or None
    row.updated_at = now
    session.commit()
    return {"rpe": row.rpe, "fatigue": row.fatigue, "soreness": row.soreness, "comment": row.comment}


def add_comment(
    session: Session,
    athlete: Athlete,
    *,
    author: str,
    body: str,
    scheduled_workout_id: int | None,
    garmin_activity_id: int | None,
) -> dict:
    text = body.strip()
    if author not in {"athlete", "coach"}:
        raise PortalInputError("Comment author must be the athlete or the coach.")
    if not text:
        raise PortalInputError("Write a comment before sending it.")
    activity = None
    if garmin_activity_id is not None:
        activity = _owned_activity(session, athlete, garmin_activity_id)
    if scheduled_workout_id is not None:
        plan = session.get(ScheduledWorkout, scheduled_workout_id)
        if plan is None or plan.athlete_id != athlete.id:
            raise PortalInputError("That workout is not on your plan.")
    if activity is None and scheduled_workout_id is None:
        raise PortalInputError("Choose a workout to comment on.")
    row = WorkoutComment(
        athlete_id=athlete.id,
        activity_id=None if activity is None else activity.id,
        scheduled_workout_id=scheduled_workout_id,
        author=author,
        body=text,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "author": row.author, "body": row.body, "created_at": row.created_at.isoformat()}


def messages(session: Session, athlete_id: int) -> list[dict]:
    rows = session.scalars(
        select(CoachMessage).where(CoachMessage.athlete_id == athlete_id).order_by(CoachMessage.id)
    ).all()
    return [
        {"id": row.id, "author": row.author, "body": row.body, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


def add_message(session: Session, athlete: Athlete, *, author: str, body: str) -> dict:
    text = body.strip()
    if author not in {"athlete", "coach"}:
        raise PortalInputError("Message author must be the athlete or the coach.")
    if not text:
        raise PortalInputError("Write a message before sending it.")
    row = CoachMessage(athlete_id=athlete.id, author=author, body=text, created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "author": row.author, "body": row.body, "created_at": row.created_at.isoformat()}


def _owned_activity(session: Session, athlete: Athlete, garmin_activity_id: int) -> Activity:
    activity = session.scalar(
        select(Activity).where(
            Activity.athlete_id == athlete.id,
            Activity.garmin_activity_id == garmin_activity_id,
        )
    )
    if activity is None:
        raise PortalInputError("That run is not in your training.")
    return activity


def _next_manual_id(session: Session, athlete_id: int) -> int:
    current = session.scalar(select(func.min(Activity.garmin_activity_id)).where(Activity.athlete_id == athlete_id))
    if current is None or current > 0:
        return -1
    return int(current) - 1


def _pace_speed(distance_meters: float | None, duration_seconds: float | None) -> float | None:
    if distance_meters is None or duration_seconds is None or duration_seconds <= 0:
        return None
    return distance_meters / duration_seconds


def log_manual(
    session: Session,
    athlete: Athlete,
    *,
    name: str,
    start_day: date,
    start_time: str | None,
    distance_miles: float | None,
    duration_seconds: float | None,
    heart_rate: float | None,
    notes: str | None,
    workout_type: str | None,
) -> dict:
    title = name.strip() or "Run"
    clock = (start_time or "12:00").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", clock):
        raise PortalInputError("Enter the start time as HH:MM.")
    distance_meters = None if distance_miles is None else distance_miles * METERS_PER_MILE
    speed = _pace_speed(distance_meters, duration_seconds)
    now = datetime.now(UTC)
    local = f"{start_day.isoformat()} {clock}:00"
    present = ["name", "start_time_local"]
    if distance_meters is not None:
        present.append("distance_meters")
    if duration_seconds is not None:
        present.append("duration_seconds")
    if heart_rate is not None:
        present.append("average_heart_rate_bpm")
    if speed is not None:
        present.append("average_speed_mps")
    activity = Activity(
        athlete_id=athlete.id,
        garmin_activity_id=_next_manual_id(session, athlete.id),
        name=title,
        activity_type_key="running",
        start_time_local=local,
        start_time_utc=now,
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        average_speed_mps=speed,
        average_heart_rate_bpm=heart_rate,
        manual_activity=True,
        present_fields=present,
        raw_summary={"source": "athlete"},
        athlete_overrides={"notes": notes.strip()} if notes and notes.strip() else None,
        import_status="manual",
        created_at=now,
        updated_at=now,
    )
    session.add(activity)
    session.flush()
    if workout_type:
        session.add(
            WorkoutClassification(
                activity_id=activity.id,
                workout_type=workout_type,
                confidence=None,
                evidence={"source": "athlete"},
                uncertainty=None,
                source="user",
                created_at=now,
            )
        )
    session.commit()
    session.refresh(activity)
    return _activity_summary(activity)


def edit_activity(
    session: Session,
    athlete: Athlete,
    garmin_activity_id: int,
    *,
    changes: dict,
) -> dict:
    activity = _owned_activity(session, athlete, garmin_activity_id)
    overrides = dict(activity.athlete_overrides or {})
    if "name" in changes and changes["name"]:
        overrides["name"] = changes["name"].strip()
        activity.name = overrides["name"]
    if "distance_miles" in changes:
        miles = changes["distance_miles"]
        meters = None if miles is None else miles * METERS_PER_MILE
        overrides["distance_meters"] = meters
        activity.distance_meters = meters
    if "duration_seconds" in changes:
        overrides["duration_seconds"] = changes["duration_seconds"]
        activity.duration_seconds = changes["duration_seconds"]
    if "average_heart_rate_bpm" in changes:
        overrides["average_heart_rate_bpm"] = changes["average_heart_rate_bpm"]
        activity.average_heart_rate_bpm = changes["average_heart_rate_bpm"]
    if "notes" in changes:
        text = (changes["notes"] or "").strip()
        overrides["notes"] = text or None
    speed = _pace_speed(activity.distance_meters, activity.duration_seconds)
    if speed is not None and ("distance_miles" in changes or "duration_seconds" in changes):
        overrides["average_speed_mps"] = speed
        activity.average_speed_mps = speed
    activity.athlete_overrides = overrides
    flag_modified(activity, "athlete_overrides")
    activity.updated_at = datetime.now(UTC)
    if "workout_type" in changes and changes["workout_type"]:
        row = session.scalar(select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id))
        now = datetime.now(UTC)
        if row is None:
            session.add(
                WorkoutClassification(
                    activity_id=activity.id,
                    workout_type=changes["workout_type"],
                    confidence=None,
                    evidence={"source": "athlete"},
                    uncertainty=None,
                    source="user",
                    created_at=now,
                )
            )
        else:
            row.workout_type = changes["workout_type"]
            row.source = "user"
    session.commit()
    session.refresh(activity)
    return _activity_summary(activity)


def activity_detail(session: Session, settings: Settings, athlete: Athlete, garmin_activity_id: int) -> dict:
    activity = _owned_activity(session, athlete, garmin_activity_id)
    today = coach_today(session, settings)
    view = _plan(session, athlete.id, today)
    planned = next(
        (
            item
            for item in view["workouts"]
            if item["match"] is not None and item["match"]["garmin_activity_id"] == garmin_activity_id
        ),
        None,
    )
    classification = session.scalar(select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id))
    summary = _activity_summary(activity)
    summary["workout_type"] = None if classification is None else classification.workout_type
    return {
        "activity": summary,
        "planned": planned,
        "feedback": _feedback_payload(
            session,
            athlete.id,
            scheduled_workout_id=None if planned is None else planned["id"],
            activity_garmin_id=garmin_activity_id,
        ),
        "comments": _comments(session, athlete.id, activity_id=activity.id),
    }


def match_workout(session: Session, athlete: Athlete, plan_id: int, garmin_activity_id: int | None) -> None:
    plan = session.get(ScheduledWorkout, plan_id)
    if plan is None or plan.athlete_id != athlete.id:
        raise PortalInputError("That workout is not on your plan.")
    if garmin_activity_id is None:
        plan.match_activity_id = None
        plan.match_source = None
    else:
        activity = _owned_activity(session, athlete, garmin_activity_id)
        plan.match_activity_id = activity.id
        plan.match_source = "athlete"
    plan.updated_at = datetime.now(UTC)
    session.commit()


def goals_payload(session: Session, athlete: Athlete) -> dict:
    goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
    races = session.scalars(select(Race).where(Race.athlete_id == athlete.id).order_by(Race.race_date, Race.id)).all()
    return {
        "primary_race_goal": None if goal is None else goal.primary_race_goal,
        "goal_race_date": None if goal is None or goal.goal_race_date is None else goal.goal_race_date.isoformat(),
        "target_time": athlete.target_time,
        "races": [_race_payload(race) for race in races],
    }


def save_goal(session: Session, settings: Settings, athlete: Athlete, *, name: str | None, race_date: date | None, target_time: str | None) -> dict:
    apply_athlete_update(
        session,
        settings,
        athlete,
        AthleteUpdate(primary_race_goal=name, goal_race_date=race_date, target_time=target_time),
    )
    session.refresh(athlete)
    return goals_payload(session, athlete)


def _known_distance(label: str | None, meters: float | None) -> float | None:
    if meters is not None and meters > 0:
        return meters
    if not label:
        return None
    text = label.strip().lower()
    for name, distance in DISTANCES:
        if name in text:
            return distance
    return None


def _race_payload(race: Race) -> dict:
    return {
        "id": race.id,
        "name": race.name,
        "race_date": None if race.race_date is None else race.race_date.isoformat(),
        "distance_label": race.distance_label,
        "distance_meters": race.distance_meters or _known_distance(race.distance_label, None),
        "goal_time": race.goal_time,
        "result_time": race.result_time,
        "notes": race.notes,
    }


def save_race(session: Session, athlete: Athlete, payload: dict, race_id: int | None = None) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise PortalInputError("Name the race.")
    if race_id is None:
        now = datetime.now(UTC)
        race = Race(athlete_id=athlete.id, name=name, created_at=now, updated_at=now)
        session.add(race)
    else:
        race = session.get(Race, race_id)
        if race is None or race.athlete_id != athlete.id:
            raise PortalInputError("That race is not on your calendar.")
        race.name = name
        race.updated_at = datetime.now(UTC)
    race.race_date = payload.get("race_date")
    race.distance_label = (payload.get("distance_label") or "").strip() or None
    race.distance_meters = _known_distance(race.distance_label, payload.get("distance_meters"))
    race.goal_time = (payload.get("goal_time") or "").strip() or None
    race.result_time = (payload.get("result_time") or "").strip() or None
    race.notes = (payload.get("notes") or "").strip() or None
    session.commit()
    session.refresh(race)
    return _race_payload(race)


def delete_race(session: Session, athlete: Athlete, race_id: int) -> None:
    race = session.get(Race, race_id)
    if race is None or race.athlete_id != athlete.id:
        raise PortalInputError("That race is not on your calendar.")
    session.delete(race)
    session.commit()


def parse_clock(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    if not re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", text):
        return None
    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def format_clock(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def race_predictions(races: list[Race]) -> dict:
    """Riegel estimate from the most recent stored result with a known distance."""
    chosen: tuple[Race, float, float] | None = None
    for race in races:
        meters = _known_distance(race.distance_label, race.distance_meters)
        seconds = parse_clock(race.result_time)
        if meters is None or seconds is None or meters <= 0 or seconds <= 0:
            continue
        if chosen is None:
            chosen = (race, meters, seconds)
            continue
        current_day = chosen[0].race_date or date.min
        next_day = race.race_date or date.min
        if next_day >= current_day:
            chosen = (race, meters, seconds)
    if chosen is None:
        return {
            "source": None,
            "estimates": [],
            "note": "A race result with a known distance is needed before a time can be estimated.",
        }
    race, meters, seconds = chosen
    estimates = []
    for label, target in PREDICTIONS:
        if abs(target - meters) / meters < 0.02:
            continue
        projected = seconds * (target / meters) ** 1.06
        estimates.append({"label": label, "time": format_clock(projected)})
    return {
        "source": {"name": race.name, "result_time": race.result_time, "distance_label": race.distance_label},
        "estimates": estimates,
        "note": "Estimated with the Riegel formula from that stored result. It is not a race plan.",
    }


def analytics(session: Session, settings: Settings, athlete: Athlete) -> dict:
    today = coach_today(session, settings)
    now = datetime.now(UTC)
    activities = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    weeks = weekly_mileage(activities, now=now, weeks=12)
    classifications = {
        row.activity_id: row.workout_type
        for row in session.scalars(
            select(WorkoutClassification).where(
                WorkoutClassification.activity_id.in_([activity.id for activity in activities] or [0])
            )
        ).all()
    }
    pace_weeks = _pace_by_week(activities, now=now)
    heart = _heart_rate_split(activities, classifications, today=today)
    load = _training_load(weeks)
    stats = running_stats(session, activities, today=today, athlete_id=athlete.id)
    races = list(session.scalars(select(Race).where(Race.athlete_id == athlete.id)).all())
    lactate = session.scalars(
        select(LactateReading).where(LactateReading.athlete_id == athlete.id).order_by(LactateReading.measured_on, LactateReading.id)
    ).all()
    threshold = session.scalar(
        select(AthleteThreshold).where(AthleteThreshold.athlete_id == athlete.id, AthleteThreshold.name == "lt2")
    )
    view = _plan(session, athlete.id, today)
    recent = [
        item
        for item in view["workouts"]
        if item["comparison"] is not None and item["scheduled_date"] <= today.isoformat()
    ]
    return {
        "weekly_mileage": weeks,
        "monthly_mileage": _monthly_mileage(activities),
        "pace_trends": pace_weeks,
        "heart_rate": heart,
        "training_load": load,
        "personal_records": {
            "best_efforts": stats["best_efforts"],
            "races": [
                _race_payload(race)
                for race in races
                if race.result_time
            ],
        },
        "planned_vs_actual": recent[-8:],
        "lactate": [_lactate_payload(row) for row in lactate],
        "threshold": None
        if threshold is None
        else {
            "pace_seconds_per_mile": threshold.pace_seconds_per_mile,
            "heart_rate_bpm": threshold.heart_rate_bpm,
        },
        "predictions": race_predictions(races),
    }


def _week_key(moment: datetime) -> date:
    day = moment.date()
    return day - timedelta(days=day.weekday())


def _pace_by_week(activities: list[Activity], *, now: datetime) -> list[dict]:
    start = _week_key(now) - timedelta(weeks=11)
    buckets: dict[date, list[float]] = {}
    for activity in activities:
        if activity.distance_meters is None or activity.duration_seconds is None or activity.duration_seconds <= 0:
            continue
        if activity.distance_meters < 1000:
            continue
        moment = activity.start_time_utc or now
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        week = _week_key(moment)
        if week < start:
            continue
        pace = activity.duration_seconds / (activity.distance_meters / METERS_PER_MILE)
        buckets.setdefault(week, []).append(pace)
    rows = []
    for index in range(12):
        week = start + timedelta(weeks=index)
        paces = buckets.get(week, [])
        rows.append(
            {
                "week_start": week.isoformat(),
                "pace_seconds_per_mile": None if not paces else sum(paces) / len(paces),
                "runs": len(paces),
            }
        )
    return rows


def _heart_rate_split(activities: list[Activity], classifications: dict[int, str], *, today: date) -> dict:
    cutoff = today - timedelta(days=28)
    easy: list[float] = []
    quality: list[float] = []
    for activity in activities:
        day = _local_day(activity)
        if day is None or day < cutoff or activity.average_heart_rate_bpm is None:
            continue
        kind = classifications.get(activity.id)
        if kind in EASY_TYPES:
            easy.append(activity.average_heart_rate_bpm)
        elif kind in QUALITY_TYPES:
            quality.append(activity.average_heart_rate_bpm)
    return {
        "easy_average_bpm": None if not easy else sum(easy) / len(easy),
        "easy_count": len(easy),
        "workout_average_bpm": None if not quality else sum(quality) / len(quality),
        "workout_count": len(quality),
        "window_days": 28,
    }


def _training_load(weeks: list[dict]) -> dict:
    miles = [week.get("distance_miles") for week in weeks]
    current = miles[-1] if miles else None
    previous = [value for value in miles[-5:-1] if isinstance(value, (int, float))]
    chronic = None if not previous else sum(previous) / len(previous)
    ratio = None
    if isinstance(current, (int, float)) and chronic:
        ratio = current / chronic
    return {
        "weeks": [
            {"week_start": week["week_start"], "distance_miles": week.get("distance_miles")}
            for week in weeks
        ],
        "this_week_miles": current,
        "previous_four_week_average": chronic,
        "acute_chronic_ratio": ratio,
    }


def _monthly_mileage(activities: list[Activity]) -> list[dict]:
    buckets: dict[str, float] = {}
    for activity in activities:
        day = _local_day(activity)
        if day is None or activity.distance_meters is None:
            continue
        key = f"{day.year:04d}-{day.month:02d}"
        buckets[key] = buckets.get(key, 0) + activity.distance_meters / METERS_PER_MILE
    return [{"month": key, "distance_miles": buckets[key]} for key in sorted(buckets)]


def _lactate_payload(row: LactateReading) -> dict:
    return {
        "id": row.id,
        "measured_on": row.measured_on.isoformat(),
        "mmol": row.mmol,
        "pace_seconds_per_mile": row.pace_seconds_per_mile,
        "heart_rate_bpm": row.heart_rate_bpm,
        "notes": row.notes,
    }


def save_lactate(
    session: Session,
    athlete: Athlete,
    *,
    measured_on: date,
    mmol: float,
    pace_seconds_per_mile: float | None,
    heart_rate_bpm: float | None,
    notes: str | None,
) -> dict:
    if mmol <= 0 or mmol > 30:
        raise PortalInputError("Enter lactate in mmol/L.")
    row = LactateReading(
        athlete_id=athlete.id,
        measured_on=measured_on,
        mmol=mmol,
        pace_seconds_per_mile=pace_seconds_per_mile,
        heart_rate_bpm=heart_rate_bpm,
        notes=(notes or "").strip() or None,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _lactate_payload(row)


def delete_lactate(session: Session, athlete: Athlete, reading_id: int) -> None:
    row = session.get(LactateReading, reading_id)
    if row is None or row.athlete_id != athlete.id:
        raise PortalInputError("That lactate reading is not saved.")
    session.delete(row)
    session.commit()
