"""Daily coaching brief from stored analyses. Athletes outside the roster are dropped."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CoachingBrief, Coach, EmailDelivery
from app.security import redact_secrets
from app.services.mailer import send_email, smtp_configured

BRIEF_PROMPT = """You write one daily briefing for a distance-running coach who manages several athletes.
Use only the roster facts supplied below. Do not invent athletes, workouts, paces, or missed sessions.
If an athlete has no stored analysis, do not describe their workout execution.
requires_attention should include athletes whose supplied reasons or adherence_notes of kind shortfall, missed, or partial are non-empty. Explain the supplied note. Do not add an athlete who is not in that evidence.
adherence_notes are calculated planned-versus-actual results. Do not recompute mileage, repetitions, or pace.
positive_developments should include athletes with a stored positive note or an adherence note of kind consistent.
Mention athletes who are completing the prescribed plan when that note is present. Do not treat a small pace difference as a failure unless the note says the workout was partial.
suggested_actions should be specific follow-ups for the coach. They are not applied to a training plan.
athlete_id and athlete_name must be copied from the roster. Do not use a name that is not in the roster.
The brief is for brief_date. Do not describe a different day as if it were brief_date.
When day_relation is not upcoming, daily_summary is the only text shown to the coach. Write it as one paragraph. Include who needs a follow-up, what went well, and what the coach should do. Do not leave that meaning for the other fields. Prefer a short briefing over a list of every workout.
When day_relation is upcoming, you are an experienced elite endurance coach writing a planned-session analysis for another coach. You know aerobic and anaerobic development, lactate threshold and aerobic threshold, VO2max, neuromuscular speed and running economy, load and fatigue, progression, and race-specific preparation. brief_date has not happened. This is not a report of a completed day.
daily_summary is the only text shown. Do not describe the workout. Explain why it was prescribed, how it should be executed, and what to judge afterward.
For each athlete with a planned workout, write the athlete name, then these sections in this order. Put a blank line between sections and between athletes. Do not repeat a point in a later section.
Workout Purpose: 2–3 sentences on the adaptation the session is meant to develop and why this session is a useful way to get it. Explain the mechanism and what the session costs. Do not define the workout type, and do not say it builds endurance or improves speed without that reasoning.
Athlete-Specific Rationale: 2–3 sentences connecting the session to prior_training when that object contains a race goal, recent training, volume, or an earlier analysis. Explain why the session fits now. If prior_training is missing or empty, give the general training rationale and do not invent a goal, a weakness, fatigue, a phase, or readiness.
Execution Guidance: 3–5 sentences on intended effort, pacing, how the faster pieces should feel, recovery, technical execution, and what to avoid. Distinguish finishing the prescription from executing it well. Use only repetitions, paces, distances, and recoveries that appear in planned_for_brief_date. Do not invent any.
Success Criteria: 2–3 concrete signs the session produced its intended adaptation. Do not treat running faster than prescribed as success.
Coach Watchpoints: the 2 or 3 observations that matter most for this workout. Say what a different outcome could indicate and what further information would help interpret it.
Training Context: 1–3 sentences on how the session sits with surrounding_workouts when that list is present, including nearby harder days and what this day should not take from them. If surrounding_workouts is missing or empty, omit this section.
If planned_for_brief_date is empty, write only that the athlete has no workout planned. Do not write the sections.
prior_training and surrounding_workouts are other days. Do not place them on brief_date. Do not mention missed sessions, adherence totals, or follow-ups for work that has not happened. Do not claim the athlete is fit, fresh, or tired unless prior_training says so.
Write in clear coach-to-coach language. Be specific. Do not use the words optimize, enhance, or maximize. Do not make every session sound equally important, and do not overstate what one session can change. Do not repeat the workout title as the analysis.
requires_attention, positive_developments, and suggested_actions must be empty arrays when day_relation is upcoming.
"""

BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "daily_summary": {"type": "string"},
        "requires_attention": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "garmin_activity_id": {"type": "integer"},
                },
                "required": ["athlete_id", "athlete_name", "reason", "garmin_activity_id"],
            },
        },
        "positive_developments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                    "note": {"type": "string"},
                    "garmin_activity_id": {"type": "integer"},
                },
                "required": ["athlete_id", "athlete_name", "note", "garmin_activity_id"],
            },
        },
        "suggested_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                    "action": {"type": "string"},
                    "garmin_activity_id": {"type": "integer"},
                },
                "required": ["athlete_id", "athlete_name", "action", "garmin_activity_id"],
            },
        },
    },
    "required": ["daily_summary", "requires_attention", "positive_developments", "suggested_actions"],
}


class _BriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    athlete_id: int
    athlete_name: str
    garmin_activity_id: int | None = None


class _Attention(_BriefItem):
    reason: str


class _Positive(_BriefItem):
    note: str


class _Action(_BriefItem):
    action: str


class CoachingBriefReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_summary: str
    requires_attention: list[_Attention]
    positive_developments: list[_Positive]
    suggested_actions: list[_Action]


def day_relation(day: date, today: date) -> str:
    if day > today:
        return "upcoming"
    if day < today:
        return "past"
    return "today"


_PRIOR_TRAINING_KEYS = (
    "race_goal",
    "weekly_miles",
    "planned_weekly_miles",
    "recent_activity",
    "stored_summary",
    "stored_positive_notes",
    "stored_effort",
    "key_workout_status",
)


def _prior_training(item: dict) -> dict:
    context: dict = {}
    for key in _PRIOR_TRAINING_KEYS:
        value = item.get(key)
        if value is None or value == "" or value == []:
            continue
        context[key] = value
    return context


def prepare_brief_payload(
    day: date,
    today: date,
    roster: list[dict],
    plans_by_athlete: dict[int, list[dict]] | None = None,
    surrounding_by_athlete: dict[int, list[dict]] | None = None,
) -> dict:
    """Shape the facts the brief is allowed to use for this calendar day."""
    relation = day_relation(day, today)
    planned = plans_by_athlete or {}
    surrounding = surrounding_by_athlete or {}
    prepared: list[dict] = []
    for item in roster:
        athlete_id = int(item["athlete_id"])
        sessions = planned.get(athlete_id, [])
        if relation == "upcoming":
            prepared.append(
                {
                    "athlete_id": athlete_id,
                    "athlete_name": item.get("athlete_name"),
                    "planned_for_brief_date": sessions,
                    "prior_training": _prior_training(item),
                    "surrounding_workouts": surrounding.get(athlete_id, []),
                }
            )
            continue
        copy = dict(item)
        copy["planned_for_brief_date"] = sessions
        prepared.append(copy)
    return {
        "brief_date": day.isoformat(),
        "brief_date_label": f"{day.strftime('%A, %B')} {day.day}",
        "day_relation": relation,
        "today": today.isoformat(),
        "roster": prepared,
    }


def validate_brief(payload: dict, allowed_ids: set[int]) -> dict:
    report = CoachingBriefReport.model_validate(payload)
    data = report.model_dump()
    text_field = {
        "requires_attention": "reason",
        "positive_developments": "note",
        "suggested_actions": "action",
    }
    for key, field in text_field.items():
        kept = []
        for item in data[key]:
            if item["athlete_id"] not in allowed_ids or not str(item.get(field) or "").strip():
                continue
            if not item.get("garmin_activity_id"):
                item["garmin_activity_id"] = None
            kept.append(item)
        data[key] = kept
    if not data["daily_summary"].strip():
        raise ValueError("daily summary is empty")
    return data


def generate_brief(
    session: Session,
    settings: Settings,
    coach: Coach,
    roster: list[dict],
    *,
    day: date | None = None,
    plans_by_athlete: dict[int, list[dict]] | None = None,
    surrounding_by_athlete: dict[int, list[dict]] | None = None,
) -> CoachingBrief:
    from app.coach.engine import _client, _completion, openai_configured

    if not openai_configured(settings):
        raise RuntimeError("openai_not_configured")
    allowed = {int(item["athlete_id"]) for item in roster}
    zone = ZoneInfo(coach.timezone or "America/New_York")
    today = datetime.now(zone).date()
    local_day = day or today
    payload = prepare_brief_payload(local_day, today, roster, plans_by_athlete, surrounding_by_athlete)
    messages = [
        {"role": "system", "content": BRIEF_PROMPT},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]
    report = None
    error = "The model returned no brief."
    for _attempt in range(2):
        completion = _completion(
            _client(settings),
            model=settings.openai_model,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "coaching_brief", "strict": True, "schema": BRIEF_SCHEMA},
            },
            messages=messages,
        )
        text = completion.choices[0].message.content or ""
        try:
            report = validate_brief(json.loads(text), allowed)
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            error = str(exc)
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "That JSON failed validation. Return a corrected object. " + error})
    if report is None:
        raise RuntimeError(f"brief_validation_failed: {error}")
    row = CoachingBrief(
        coach_id=coach.id,
        brief_date=local_day,
        status="ready",
        model=settings.openai_model,
        report=report,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest_brief(session: Session, coach: Coach) -> CoachingBrief | None:
    return session.scalar(
        select(CoachingBrief).where(CoachingBrief.coach_id == coach.id).order_by(CoachingBrief.id.desc()).limit(1)
    )


def brief_for_day(session: Session, coach: Coach, day: date) -> CoachingBrief | None:
    """Return the newest brief written for this calendar day. Other days stay hidden."""
    return session.scalar(
        select(CoachingBrief)
        .where(CoachingBrief.coach_id == coach.id, CoachingBrief.brief_date == day)
        .order_by(CoachingBrief.id.desc())
        .limit(1)
    )


def brief_email_body(settings: Settings, report: dict, roster: list[dict] | None = None) -> str:
    lines = [report.get("daily_summary") or "", "", "Requires attention"]
    attention = report.get("requires_attention") or []
    lines.extend(_lines(settings, attention, "reason") or ["None from the stored activities."])
    lines.extend(["", "Positive developments"])
    lines.extend(_lines(settings, report.get("positive_developments") or [], "note") or ["None recorded."])
    lines.extend(["", "Suggested coach actions"])
    lines.extend(_lines(settings, report.get("suggested_actions") or [], "action") or ["None recorded."])
    lines.extend(["", "Planned versus actual"])
    planned = []
    for item in roster or []:
        for note in item.get("adherence_notes") or []:
            if note.get("kind") not in {"shortfall", "missed", "partial", "consistent", "progress"}:
                continue
            planned.append(f"- {item.get('athlete_name')}: {note.get('note')} ({settings.public_app_url.rstrip('/')}/athletes/{item.get('athlete_id')}?section=plan)")
    lines.extend(planned or ["No planned-versus-actual results are stored."])
    return "\n".join(lines)


def _lines(settings: Settings, items: list[dict], field: str) -> list[str]:
    rendered = []
    for item in items:
        link = f"{settings.public_app_url.rstrip('/')}/athletes/{item['athlete_id']}"
        activity = item.get("garmin_activity_id")
        if activity:
            link = f"{settings.public_app_url.rstrip('/')}/activities/{activity}"
        rendered.append(f"- {item.get('athlete_name')}: {item.get(field)} ({link})")
    return rendered


def deliver_daily_brief(session: Session, settings: Settings, coach: Coach, roster: list[dict]) -> str:
    """Send at most one brief email per local day, and only when the coach enabled it."""
    if not coach.email_notifications_enabled:
        return "disabled"
    zone = ZoneInfo(coach.timezone or "America/New_York")
    local_now = datetime.now(zone)
    if local_now.hour != 7:
        return "outside_delivery_hour"
    already = session.scalar(
        select(EmailDelivery).where(
            EmailDelivery.coach_id == coach.id,
            EmailDelivery.brief_date == local_now.date(),
            EmailDelivery.status == "sent",
        )
    )
    if already is not None:
        return "already_sent"
    if not coach.email:
        _record(session, coach, local_now.date(), "skipped", "No coach email is saved.")
        return "missing_email"
    if not smtp_configured(settings):
        _record(session, coach, local_now.date(), "skipped", "SMTP is not configured.")
        return "email_not_configured"
    brief = session.scalar(
        select(CoachingBrief).where(
            CoachingBrief.coach_id == coach.id,
            CoachingBrief.brief_date == local_now.date(),
            CoachingBrief.status == "ready",
        ).order_by(CoachingBrief.id.desc())
    )
    if brief is None:
        brief = generate_brief(session, settings, coach, roster)
    try:
        send_email(
            settings,
            recipient=coach.email,
            subject=f"Coaching brief {local_now.date().isoformat()}",
            body=brief_email_body(settings, brief.report or {}, roster),
        )
    except Exception as exc:
        _record(session, coach, local_now.date(), "failed", redact_secrets(str(exc)))
        return "failed"
    _record(session, coach, local_now.date(), "sent", None, recipient=coach.email)
    return "sent"


def _record(session: Session, coach: Coach, brief_date, status: str, detail: str | None, recipient: str | None = None) -> None:
    session.add(
        EmailDelivery(
            coach_id=coach.id,
            brief_date=brief_date,
            recipient=recipient or coach.email,
            status=status,
            detail=detail,
            sent_at=datetime.now(UTC),
        )
    )
    session.commit()
