"""One Coach's Review paragraph for one athlete and one day.

The paragraph is written from the stored workout analysis, the existing
plan match, and tomorrow's planned workout. It does not detect workouts,
read FIT files, or regenerate the detailed analysis.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.garmin.mapping import pace_seconds_per_mile
from app.models import Activity, ActivityLap, Athlete, CoachReview, ScheduledWorkout, WorkoutAnalysis, WorkoutClassification, WorkoutFeedback
from app.coach.engine import present_report
from app.services.adherence import (
    _local_day,
    assign_matches,
    compare_execution,
    format_pace,
    miles_from_meters,
    repetition_measurements,
)

AWAITING_ACTIVITY = "Awaiting completed activity. Coach's Review will be available once the workout is recorded."
AWAITING_ANALYSIS = "The activity is recorded. Coach's Review will be available once the detailed analysis is stored."

REVIEW_PROMPT = """You write one Coach's Review for a single athlete on a single calendar day.
Use only the JSON packet. Do not invent paces, distances, durations, repetitions, heart rates, soreness, fatigue, fitness changes, or a workout that is not in the packet.
stored_analysis is an existing interpretation of that activity. Use it as the finding. Do not replace its workout classification or its stimulus.
planned_versus_actual is already calculated. Do not recompute mileage, repetitions, or pace. actual_pace_basis says what the pace number is. stored_work_intervals means the pace is the work intervals. whole_run_average means the pace is the whole run, not the intervals. Do not describe a whole-run average as interval pace. Do not treat a recovery jog as a failed work interval. Do not judge the session only by average pace.
matched_sessions pairs each planned workout with the activity the existing matcher assigned. unmatched_activities are separate recorded runs. Do not fold an unmatched run into a planned workout, and do not combine separate runs into one session.
If planned_workouts is empty, do not claim the athlete followed or missed a plan.
If a planned workout has confirmed_missed true, do not claim that workout was completed.
If tomorrow is null, do not invent the next session. Say that the next session is not scheduled.
athlete_feedback is included only when the athlete recorded it. Do not infer effort, soreness, or recovery when it is absent.
recent_sessions and prior_seven_day_miles are other days. Use them only when they are present. One pace or heart rate cannot establish fatigue, readiness, improved fitness, or injury risk. Keep an observed fact separate from a possible explanation.
Write one paragraph of 90 to 130 words. No title, headings, bullets, labels, or line breaks.
Move from what was done and how it compared with the prescription, to the two or three findings that matter, to what that means for tomorrow's planned workout.
Suggest a change only when stored_analysis or planned_versus_actual supports it. Name the direction, such as reduced intensity, shorter duration, or more recovery. Do not edit the plan. If the evidence does not support a change, say the planned session can stay as written.
Do not open with the athlete's name, and do not repeat it. Do not praise without a stated observation. Do not use the phrases Great job, Solid session, Nice work, or Well done.
Do not use the words optimize, enhance, or maximize.
Return JSON with one field, paragraph.
"""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"paragraph": {"type": "string"}},
    "required": ["paragraph"],
}


def review_for_athlete(session: Session, settings: Settings, athlete: Athlete, day: date, *, complete=None) -> dict:
    """Return the paragraph for this athlete and day. Waiting states skip the model."""
    packet, source = _packet(session, athlete, day)
    if packet is None:
        return {"status": "waiting", "paragraph": AWAITING_ACTIVITY, "cached": False}
    if packet.get("stored_analysis_missing"):
        return {"status": "waiting", "paragraph": AWAITING_ANALYSIS, "cached": False}
    key = hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()
    stored = session.scalar(
        select(CoachReview)
        .where(CoachReview.athlete_id == athlete.id, CoachReview.review_date == day, CoachReview.source_key == key)
        .order_by(CoachReview.id.desc())
        .limit(1)
    )
    if stored is not None:
        return {"status": "ready", "paragraph": stored.paragraph, "cached": True}
    writer = complete or _gemini_paragraph
    if complete is None:
        from app.coach.gemini import gemini_configured

        if not gemini_configured(settings):
            raise RuntimeError("gemini_not_configured")
    athlete_id = athlete.id
    model = None if complete is not None or settings is None else settings.gemini_model
    session.commit()
    messages = [
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": json.dumps(packet, default=str)},
    ]
    paragraph = None
    error = "The model returned no review."
    for _attempt in range(2):
        text = writer(settings, messages)
        try:
            paragraph = _validate_paragraph(text)
            break
        except (json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "That JSON failed validation. Return a corrected object. " + error})
    if paragraph is None:
        raise RuntimeError(f"review_validation_failed: {error}")
    row = CoachReview(
        athlete_id=athlete_id,
        review_date=day,
        source_key=key,
        model=model,
        paragraph=paragraph,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        row = session.scalar(
            select(CoachReview).where(
                CoachReview.athlete_id == athlete_id,
                CoachReview.review_date == day,
                CoachReview.source_key == key,
            )
        )
        if row is None:
            raise
    return {"status": "ready", "paragraph": row.paragraph, "cached": False}


def _gemini_paragraph(settings: Settings, messages: list[dict]) -> str:
    from app.coach.gemini import complete_messages

    return complete_messages(
        settings,
        model=settings.gemini_model,
        response_format={"type": "json_schema", "json_schema": {"name": "coach_review", "strict": True, "schema": REVIEW_SCHEMA}},
        messages=messages,
    )


def _validate_paragraph(text: str) -> str:
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != {"paragraph"} or not isinstance(data.get("paragraph"), str):
        raise ValueError("paragraph must be the only field")
    paragraph = " ".join(data["paragraph"].split())
    if not paragraph:
        raise ValueError("paragraph is empty")
    if re.search(r"(^|\s)[-*•]\s", paragraph) or paragraph.startswith("#"):
        raise ValueError("paragraph must be one paragraph without bullets or headings")
    words = paragraph.split()
    if not 80 <= len(words) <= 140:
        raise ValueError(f"paragraph is {len(words)} words; write 90 to 130 words")
    if re.search(r"\b(great job|solid session|nice work|well done)\b", paragraph, re.I):
        raise ValueError("paragraph uses generic praise")
    return paragraph


def _packet(session: Session, athlete: Athlete, day: date) -> tuple[dict | None, dict]:
    recent_start = (day - timedelta(days=21)).isoformat()
    day_end = (day + timedelta(days=1)).isoformat()
    activities = list(
        session.scalars(
            select(Activity)
            .where(
                Activity.athlete_id == athlete.id,
                Activity.start_time_local >= recent_start,
                Activity.start_time_local < day_end,
            )
            .order_by(Activity.start_time_local)
        ).all()
    )
    plans = list(
        session.scalars(
            select(ScheduledWorkout)
            .where(
                ScheduledWorkout.athlete_id == athlete.id,
                ScheduledWorkout.scheduled_date >= day,
                ScheduledWorkout.scheduled_date <= day + timedelta(days=1),
            )
            .order_by(ScheduledWorkout.scheduled_date, ScheduledWorkout.id)
        ).all()
    )
    day_plans = [plan for plan in plans if plan.scheduled_date == day]
    tomorrow_plans = [plan for plan in plans if plan.scheduled_date == day + timedelta(days=1)]
    by_id = {activity.id: activity for activity in activities}
    manual_ids = [
        plan.match_activity_id
        for plan in day_plans
        if plan.match_source == "manual" and plan.match_activity_id not in by_id and plan.match_activity_id is not None
    ]
    if manual_ids:
        for activity in session.scalars(
            select(Activity).where(Activity.athlete_id == athlete.id, Activity.id.in_(manual_ids))
        ).all():
            activities.append(activity)
            by_id[activity.id] = activity
    day_activities = [activity for activity in activities if _local_day(activity) == day]
    for plan in day_plans:
        if plan.match_source == "manual" and plan.match_activity_id in by_id and by_id[plan.match_activity_id] not in day_activities:
            day_activities.append(by_id[plan.match_activity_id])
    if not day_activities:
        return None, {}
    activity_ids = [activity.id for activity in activities]
    classifications = {
        row.activity_id: row
        for row in session.scalars(select(WorkoutClassification).where(WorkoutClassification.activity_id.in_(activity_ids))).all()
    }
    analyses = _latest_analyses(session, activity_ids)
    types = {activity_id: row.workout_type for activity_id, row in classifications.items()}
    assigned = assign_matches(day_plans, day_activities, types)
    matched_ids = [activity.id for activity in assigned.values()]
    laps: dict[int, list] = {}
    if matched_ids:
        for lap in session.scalars(select(ActivityLap).where(ActivityLap.activity_id.in_(matched_ids)).order_by(ActivityLap.lap_number)).all():
            laps.setdefault(lap.activity_id, []).append(lap)
    used = {activity.id for activity in assigned.values()}
    matched_sessions = []
    for plan in day_plans:
        activity = assigned.get(plan.id)
        matched_sessions.append(_matched(plan, activity, classifications.get(None if activity is None else activity.id), analyses.get(None if activity is None else activity.id), laps.get(None if activity is None else activity.id, [])))
    unmatched = [_activity_facts(activity, classifications.get(activity.id), analyses.get(activity.id), comparison=None) for activity in day_activities if activity.id not in used]
    analyzed = [item for item in matched_sessions if item.get("stored_analysis")] + [item for item in unmatched if item.get("stored_analysis")]
    feedback = _feedback(session, athlete.id, [activity.id for activity in day_activities], [plan.id for plan in day_plans])
    source = {
        "day": day.isoformat(),
        "activities": [
            {
                "id": activity.id,
                "distance_meters": activity.distance_meters,
                "duration_seconds": activity.duration_seconds,
                "analysis_id": None if analyses.get(activity.id) is None else analyses[activity.id].id,
                "workout_type": types.get(activity.id),
            }
            for activity in day_activities
        ],
        "plans": [
            {
                "id": plan.id,
                "updated_at": _stamp(plan.updated_at or plan.created_at),
                "match_activity_id": plan.match_activity_id,
                "match_source": plan.match_source,
            }
            for plan in day_plans
        ],
        "tomorrow": [{"id": plan.id, "updated_at": _stamp(plan.updated_at or plan.created_at)} for plan in tomorrow_plans],
        "feedback": feedback["source"],
    }
    if not analyzed:
        return {"stored_analysis_missing": True}, source
    recent = []
    for activity in reversed(activities):
        local = _local_day(activity)
        if local is None or local >= day or local < day - timedelta(days=21):
            continue
        recent.append(_recent(activity, classifications.get(activity.id), analyses.get(activity.id)))
        if len(recent) == 8:
            break
    packet = {
        "review_date": day.isoformat(),
        "planned_workouts": [_plan_facts(plan) for plan in day_plans],
        "matched_sessions": matched_sessions,
        "unmatched_activities": unmatched,
        "athlete_feedback": feedback["shown"],
        "recent_sessions": recent,
        "prior_seven_day_miles": _prior_miles(activities, day),
        "tomorrow": None if not tomorrow_plans else [_plan_facts(plan) for plan in tomorrow_plans],
    }
    return packet, source


def _matched(plan, activity, classification, analysis, laps: list) -> dict:
    facts = _plan_facts(plan)
    facts["confirmed_missed"] = plan.match_source == "confirmed_missed"
    if activity is None:
        facts["activity"] = None
        facts["planned_versus_actual"] = None
        facts["stored_analysis"] = None
        return facts
    evidence = None if classification is None or not isinstance(classification.evidence, dict) else classification.evidence
    count, pace, rep_distance, recovery = repetition_measurements(laps, evidence)
    comparison = compare_execution(
        plan,
        activity,
        actual_type=None if classification is None else classification.workout_type,
        repetition_count=count,
        repetition_pace=pace,
        repetition_distance_meters=rep_distance,
        recovery_seconds=recovery,
        recorded_effort=None,
    )
    comparison = dict(comparison)
    comparison["actual_pace_basis"] = "stored_work_intervals" if pace is not None else "whole_run_average" if comparison.get("actual_pace_seconds_per_mile") is not None else None
    facts["activity"] = _activity_facts(activity, classification, analysis, comparison)["activity"]
    facts["planned_versus_actual"] = _comparison_facts(comparison)
    facts["stored_analysis"] = _stored_analysis(None if analysis is None else analysis.report)
    return facts


def _activity_facts(activity, classification, analysis, comparison) -> dict:
    pace = pace_seconds_per_mile(activity.average_speed_mps)
    return {
        "activity": {
            "name": activity.name,
            "distance_miles": _miles(activity.distance_meters),
            "duration_seconds": None if activity.duration_seconds is None else round(activity.duration_seconds),
            "whole_run_average_pace": format_pace(pace),
            "stored_workout_type": None if classification is None else classification.workout_type,
        },
        "planned_versus_actual": None if comparison is None else _comparison_facts(comparison),
        "stored_analysis": _stored_analysis(None if analysis is None else analysis.report),
    }


def _comparison_facts(comparison: dict) -> dict:
    kept = {
        "execution": comparison.get("execution"),
        "summary": comparison.get("summary"),
        "planned_distance_miles": _round(comparison.get("planned_distance_miles")),
        "actual_distance_miles": _round(comparison.get("actual_distance_miles")),
        "distance_difference_miles": _round(comparison.get("distance_difference_miles")),
        "planned_pace": format_pace(comparison.get("planned_pace_seconds_per_mile")),
        "actual_pace": format_pace(comparison.get("actual_pace_seconds_per_mile")),
        "actual_pace_basis": comparison.get("actual_pace_basis"),
        "pace_difference_seconds_per_mile": None if comparison.get("pace_difference_seconds_per_mile") is None else round(comparison["pace_difference_seconds_per_mile"]),
        "planned_repetitions": comparison.get("planned_repetitions"),
        "actual_repetitions": comparison.get("actual_repetitions"),
        "planned_recovery_seconds": comparison.get("planned_recovery_seconds"),
        "actual_recovery_seconds": None if comparison.get("actual_recovery_seconds") is None else round(comparison["actual_recovery_seconds"]),
        "planned_workout_type": comparison.get("planned_workout_type"),
        "actual_workout_type": comparison.get("actual_workout_type"),
    }
    return {key: value for key, value in kept.items() if value is not None}


def _plan_facts(plan: ScheduledWorkout) -> dict:
    facts = {
        "scheduled_date": plan.scheduled_date.isoformat(),
        "title": plan.title,
        "workout_type": plan.workout_type,
        "details": _clip(plan.details, 500),
        "distance_miles": _miles(plan.distance_meters),
        "target_pace": format_pace(plan.target_pace_seconds_per_mile),
        "repetitions": plan.repetitions,
        "rep_distance_miles": _miles(plan.rep_distance_meters),
        "recovery_seconds": plan.recovery_seconds,
        "warmup": _clip(plan.warmup, 240),
        "cooldown": _clip(plan.cooldown, 240),
        "intensity": plan.intensity,
        "coach_notes": _clip(plan.coach_notes, 400),
    }
    return {key: value for key, value in facts.items() if value is not None}


def _stored_analysis(report: dict | None) -> dict | None:
    if not isinstance(report, dict):
        return None
    shown = present_report(report, workout_type=None, distance_meters=None, average_speed_mps=None) or {}
    assessment = shown.get("coaching_assessment") if isinstance(shown.get("coaching_assessment"), dict) else {}
    findings = assessment.get("ranked_findings") if isinstance(assessment.get("ranked_findings"), list) else []
    excerpt = {
        "workout_analysis": _clip(shown.get("workout_analysis") or shown.get("summary") or shown.get("execution_analysis")),
        "training_impact": _clip(shown.get("training_impact")),
        "coach_takeaway": _clip(shown.get("coach_takeaway")),
        "execution_judgment": _clip(assessment.get("execution_judgment"), 400),
        "primary_stimulus": _clip(assessment.get("primary_stimulus"), 300),
        "adjustment": assessment.get("adjustment") if assessment.get("adjustment") in {"continue", "adjust", "insufficient_evidence"} else None,
        "historical_context": _clip(assessment.get("historical_context"), 400),
        "material_limitations": [item for item in (_clip(piece, 200) for piece in assessment.get("material_limitations") or [] if isinstance(piece, str)) if item][:4],
        "ranked_findings": [item for item in (_clip(piece, 240) for piece in findings if isinstance(piece, str)) if item][:4],
    }
    if not any(excerpt.get(key) for key in ("workout_analysis", "training_impact", "coach_takeaway", "execution_judgment", "primary_stimulus")):
        return None
    return {key: value for key, value in excerpt.items() if value not in (None, [], "")}


def _recent(activity, classification, analysis) -> dict:
    excerpt = _stored_analysis(None if analysis is None else analysis.report)
    facts = {
        "date": None if _local_day(activity) is None else _local_day(activity).isoformat(),
        "distance_miles": _miles(activity.distance_meters),
        "stored_workout_type": None if classification is None else classification.workout_type,
        "stored_analysis": None if excerpt is None else excerpt.get("workout_analysis") or excerpt.get("coach_takeaway"),
    }
    return {key: value for key, value in facts.items() if value is not None}


def _feedback(session: Session, athlete_id: int, activity_ids: list[int], plan_ids: list[int]) -> dict:
    if not activity_ids and not plan_ids:
        return {"shown": None, "source": []}
    rows = list(
        session.scalars(
            select(WorkoutFeedback)
            .where(WorkoutFeedback.athlete_id == athlete_id)
            .where(
                or_(
                    WorkoutFeedback.activity_id.in_(activity_ids or [0]),
                    WorkoutFeedback.scheduled_workout_id.in_(plan_ids or [0]),
                )
            )
        ).all()
    )
    shown = []
    source = []
    for row in rows:
        item = {
            "rpe": row.rpe,
            "fatigue": row.fatigue,
            "soreness": row.soreness,
            "comment": _clip(row.comment, 300),
        }
        cleaned = {key: value for key, value in item.items() if value is not None}
        if cleaned:
            shown.append(cleaned)
        source.append({"id": row.id, "updated_at": _stamp(row.updated_at), "rpe": row.rpe, "fatigue": row.fatigue, "soreness": row.soreness, "comment": row.comment})
    return {"shown": shown or None, "source": source}


def _prior_miles(activities: list, day: date) -> float | None:
    start = day - timedelta(days=7)
    distances = [
        activity.distance_meters
        for activity in activities
        if activity.distance_meters is not None and (local := _local_day(activity)) is not None and start <= local < day
    ]
    if not distances:
        return None
    return round(sum(distances) / 1609.344, 1)


def _latest_analyses(session: Session, activity_ids: list[int]) -> dict[int, WorkoutAnalysis]:
    if not activity_ids:
        return {}
    found: dict[int, WorkoutAnalysis] = {}
    rows = session.scalars(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id.in_(activity_ids), WorkoutAnalysis.status == "ready")
        .order_by(WorkoutAnalysis.id.desc())
    ).all()
    for row in rows:
        found.setdefault(row.activity_id, row)
    return found


def _miles(meters: float | None) -> float | None:
    miles = miles_from_meters(meters)
    return None if miles is None else round(miles, 2)


def _round(value) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


def _clip(value, limit: int = 700) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _stamp(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
