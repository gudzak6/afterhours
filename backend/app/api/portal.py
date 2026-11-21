"""Athlete portal HTTP API. Coach notes and Garmin keys are never returned."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes import _athlete_out, _sync_status_code
from app.coach.engine import chat, openai_configured, safe_error
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Athlete
from app.schemas import AthleteIntake, ChatMessageOut, SyncJobOut
from app.services.portal import (
    PortalInputError,
    activity_detail,
    add_comment,
    add_message,
    analytics,
    calendar_month,
    delete_lactate,
    delete_race,
    edit_activity,
    garmin_state,
    goals_payload,
    home,
    recent_runs,
    intake_complete,
    join_athlete,
    log_manual,
    match_workout,
    messages,
    save_feedback,
    save_garmin_login,
    save_goal,
    save_lactate,
    save_race,
    week_view,
    workout_detail,
)
from app.services.sync import SyncInProgress, ensure_coach, run_sync

router = APIRouter()


class JoinIn(BaseModel):
    intake: AthleteIntake
    athlete_id: int | None = None


class GarminSignIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    mfa_code: str | None = Field(default=None, max_length=20)


class GoalIn(BaseModel):
    primary_race_goal: str | None = None
    goal_race_date: date | None = None
    target_time: str | None = Field(default=None, max_length=40)


class RaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    race_date: date | None = None
    distance_label: str | None = Field(default=None, max_length=80)
    distance_meters: float | None = None
    goal_time: str | None = Field(default=None, max_length=40)
    result_time: str | None = Field(default=None, max_length=40)
    notes: str | None = None


class ManualActivityIn(BaseModel):
    name: str = ""
    start_day: date
    start_time: str | None = None
    distance_miles: float | None = None
    duration_seconds: float | None = None
    average_heart_rate_bpm: float | None = None
    notes: str | None = None
    workout_type: str | None = None


class ActivityEditIn(BaseModel):
    name: str | None = None
    distance_miles: float | None = None
    duration_seconds: float | None = None
    average_heart_rate_bpm: float | None = None
    notes: str | None = None
    workout_type: str | None = None


class FeedbackIn(BaseModel):
    scheduled_workout_id: int | None = None
    garmin_activity_id: int | None = None
    rpe: int | None = None
    fatigue: int | None = None
    soreness: int | None = None
    comment: str | None = None


class CommentIn(BaseModel):
    author: str = "athlete"
    body: str
    scheduled_workout_id: int | None = None
    garmin_activity_id: int | None = None


class MessageIn(BaseModel):
    author: str = "athlete"
    body: str


class MatchIn(BaseModel):
    garmin_activity_id: int | None = None


class LactateIn(BaseModel):
    measured_on: date
    mmol: float
    pace_seconds_per_mile: float | None = None
    heart_rate_bpm: float | None = None
    notes: str | None = None


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    garmin_activity_id: int | None = None


def _athlete(db: Session, settings: Settings, athlete_id: int) -> Athlete:
    coach = ensure_coach(db, settings)
    athlete = db.get(Athlete, athlete_id)
    if athlete is None or athlete.coach_id != coach.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Athlete not found"})
    return athlete


def _guard_secret(payload: dict, secret: str) -> None:
    watched = {"garmin": payload.get("garmin"), "sync": payload.get("sync")}
    if secret and secret in str(watched):
        raise HTTPException(status_code=500, detail={"code": "secret_leaked", "message": "The Garmin password was not stored safely."})


def _input(exc: PortalInputError) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})


def _status(db: Session, settings: Settings, athlete: Athlete) -> dict:
    coach = ensure_coach(db, settings)
    profile = _athlete_out(db, athlete, settings).model_dump(mode="json")
    profile["coach_notes"] = None
    return {
        "athlete": profile,
        "intake_complete": intake_complete(athlete.intake if isinstance(athlete.intake, dict) else None),
        "garmin": garmin_state(db, athlete.id),
        "coach_name": coach.display_name,
        "openai_configured": openai_configured(settings),
    }


@router.post("/api/portal/join")
def portal_join(body: JoinIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    try:
        athlete = join_athlete(db, settings, body.intake, body.athlete_id)
    except PortalInputError as exc:
        raise _input(exc) from exc
    return _status(db, settings, athlete)


@router.get("/api/portal/{athlete_id}")
def portal_status(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return _status(db, settings, _athlete(db, settings, athlete_id))


@router.post("/api/portal/{athlete_id}/garmin")
def portal_connect(
    athlete_id: int,
    body: GarminSignIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _athlete(db, settings, athlete_id)
    from app.garmin.connect import GarminMfaRequired

    try:
        token = save_garmin_login(db, athlete, body.email, body.password, body.mfa_code)
    except GarminMfaRequired as exc:
        payload = _status(db, settings, athlete)
        payload["mfa_required"] = True
        payload["garmin"]["last_error"] = str(exc)
        _guard_secret(payload, body.password)
        return payload
    except PortalInputError as exc:
        raise _input(exc) from exc
    try:
        job = run_sync(db, settings, trigger="manual", athlete_id=athlete.id, connect_token=token)
    except SyncInProgress as exc:
        raise HTTPException(status_code=409, detail={"code": "sync_in_progress", "message": str(exc)}) from exc
    payload = _status(db, settings, athlete)
    payload["sync"] = SyncJobOut.from_job(job).model_dump(mode="json")
    if _sync_status_code(job) != 200:
        payload["garmin"]["connected"] = False
    _guard_secret(payload, body.password)
    return payload


@router.post("/api/portal/{athlete_id}/garmin/sync")
def portal_sync(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    athlete = _athlete(db, settings, athlete_id)
    state = garmin_state(db, athlete.id)
    if not state["key_saved"]:
        raise HTTPException(status_code=422, detail={"code": "garmin_not_connected", "message": "Connect Garmin before syncing."})
    from app.models import GarminConnection
    from sqlalchemy import select

    connection = db.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
    token = "" if connection is None else (connection.connect_token or "").strip()
    key = "" if connection is None else (connection.personal_api_key or "").strip()
    try:
        job = run_sync(
            db,
            settings,
            trigger="manual",
            athlete_id=athlete.id,
            api_key=None if token else key,
            connect_token=token or None,
        )
    except SyncInProgress as exc:
        raise HTTPException(status_code=409, detail={"code": "sync_in_progress", "message": str(exc)}) from exc
    payload = SyncJobOut.from_job(job).model_dump(mode="json")
    status_code = _sync_status_code(job)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.get("/api/portal/{athlete_id}/home")
def portal_home(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return home(db, settings, _athlete(db, settings, athlete_id))


@router.get("/api/portal/{athlete_id}/calendar")
def portal_calendar(
    athlete_id: int,
    month: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return calendar_month(db, settings, _athlete(db, settings, athlete_id), month)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.get("/api/portal/{athlete_id}/week")
def portal_week(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return week_view(db, settings, _athlete(db, settings, athlete_id))


@router.get("/api/portal/{athlete_id}/workouts/{plan_id}")
def portal_workout(
    athlete_id: int,
    plan_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    workout = workout_detail(db, settings, _athlete(db, settings, athlete_id), plan_id)
    if workout is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Planned workout not found"})
    return workout


@router.get("/api/portal/{athlete_id}/activities")
def portal_activities(
    athlete_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _athlete(db, settings, athlete_id)
    bounded = min(max(limit, 1), 200)
    return {"activities": recent_runs(db, athlete.id, bounded)}


@router.get("/api/portal/{athlete_id}/activities/{garmin_activity_id}")
def portal_activity(
    athlete_id: int,
    garmin_activity_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return activity_detail(db, settings, _athlete(db, settings, athlete_id), garmin_activity_id)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.post("/api/portal/{athlete_id}/activities")
def portal_log(
    athlete_id: int,
    body: ManualActivityIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return log_manual(
            db,
            _athlete(db, settings, athlete_id),
            name=body.name,
            start_day=body.start_day,
            start_time=body.start_time,
            distance_miles=body.distance_miles,
            duration_seconds=body.duration_seconds,
            heart_rate=body.average_heart_rate_bpm,
            notes=body.notes,
            workout_type=body.workout_type,
        )
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.patch("/api/portal/{athlete_id}/activities/{garmin_activity_id}")
def portal_edit_activity(
    athlete_id: int,
    garmin_activity_id: int,
    body: ActivityEditIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    try:
        return edit_activity(db, _athlete(db, settings, athlete_id), garmin_activity_id, changes=changes)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.post("/api/portal/{athlete_id}/feedback")
def portal_feedback(
    athlete_id: int,
    body: FeedbackIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return save_feedback(
            db,
            _athlete(db, settings, athlete_id),
            scheduled_workout_id=body.scheduled_workout_id,
            garmin_activity_id=body.garmin_activity_id,
            rpe=body.rpe,
            fatigue=body.fatigue,
            soreness=body.soreness,
            comment=body.comment,
        )
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.post("/api/portal/{athlete_id}/comments")
def portal_comment(
    athlete_id: int,
    body: CommentIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return add_comment(
            db,
            _athlete(db, settings, athlete_id),
            author=body.author,
            body=body.body,
            scheduled_workout_id=body.scheduled_workout_id,
            garmin_activity_id=body.garmin_activity_id,
        )
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.get("/api/portal/{athlete_id}/messages")
def portal_messages(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    athlete = _athlete(db, settings, athlete_id)
    return {"messages": messages(db, athlete.id)}


@router.post("/api/portal/{athlete_id}/messages")
def portal_message(
    athlete_id: int,
    body: MessageIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return add_message(db, _athlete(db, settings, athlete_id), author=body.author, body=body.body)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.patch("/api/portal/{athlete_id}/workouts/{plan_id}/match")
def portal_match(
    athlete_id: int,
    plan_id: int,
    body: MatchIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        match_workout(db, _athlete(db, settings, athlete_id), plan_id, body.garmin_activity_id)
    except PortalInputError as exc:
        raise _input(exc) from exc
    return {"id": plan_id}


@router.get("/api/portal/{athlete_id}/goals")
def portal_goals(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return goals_payload(db, _athlete(db, settings, athlete_id))


@router.patch("/api/portal/{athlete_id}/goals")
def portal_save_goal(
    athlete_id: int,
    body: GoalIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return save_goal(
        db,
        settings,
        _athlete(db, settings, athlete_id),
        name=body.primary_race_goal,
        race_date=body.goal_race_date,
        target_time=body.target_time,
    )


@router.post("/api/portal/{athlete_id}/races")
def portal_add_race(
    athlete_id: int,
    body: RaceIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return save_race(db, _athlete(db, settings, athlete_id), body.model_dump())
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.patch("/api/portal/{athlete_id}/races/{race_id}")
def portal_edit_race(
    athlete_id: int,
    race_id: int,
    body: RaceIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return save_race(db, _athlete(db, settings, athlete_id), body.model_dump(), race_id)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.delete("/api/portal/{athlete_id}/races/{race_id}", status_code=204)
def portal_delete_race(
    athlete_id: int,
    race_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    try:
        delete_race(db, _athlete(db, settings, athlete_id), race_id)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.get("/api/portal/{athlete_id}/analytics")
def portal_analytics(athlete_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return analytics(db, settings, _athlete(db, settings, athlete_id))


@router.post("/api/portal/{athlete_id}/lactate")
def portal_lactate(
    athlete_id: int,
    body: LactateIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return save_lactate(
            db,
            _athlete(db, settings, athlete_id),
            measured_on=body.measured_on,
            mmol=body.mmol,
            pace_seconds_per_mile=body.pace_seconds_per_mile,
            heart_rate_bpm=body.heart_rate_bpm,
            notes=body.notes,
        )
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.delete("/api/portal/{athlete_id}/lactate/{reading_id}", status_code=204)
def portal_delete_lactate(
    athlete_id: int,
    reading_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    try:
        delete_lactate(db, _athlete(db, settings, athlete_id), reading_id)
    except PortalInputError as exc:
        raise _input(exc) from exc


@router.post("/api/portal/{athlete_id}/assistant")
def portal_assistant(
    athlete_id: int,
    body: AssistantIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    athlete = _athlete(db, settings, athlete_id)
    if not openai_configured(settings):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openai_not_configured",
                "message": "Add OPENAI_API_KEY to the API environment. The assistant will not invent an answer.",
            },
        )
    try:
        conversation, stored = chat(
            db,
            settings,
            athlete,
            message=body.message,
            conversation_id=body.conversation_id,
            garmin_activity_id=body.garmin_activity_id,
            audience="athlete",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "openai_error", "message": safe_error(exc)}) from exc
    return {
        "conversation_id": conversation.id,
        "messages": [
            ChatMessageOut(id=item.id, role=item.role, content=item.content, created_at=item.created_at).model_dump(mode="json")
            for item in stored
        ],
    }
