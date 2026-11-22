"""Coaching reports and chat. The model does not calculate metrics or change a plan."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.garmin.mapping import pace_seconds_per_mile
from app.metrics.engine import activity_metrics
from app.services.history import training_history
from app.services.mileage import window_stats
from app.models import (
    Activity,
    ActivityLap,
    ActivitySample,
    AiConversation,
    AiMessage,
    Athlete,
    AthleteThreshold,
    ScheduledWorkout,
    TrainingGoal,
    WorkoutAnalysis,
    WorkoutClassification,
)
from app.security import redact_secrets

SYSTEM_PROMPT = """You brief a knowledgeable competitive running coach.
Use only numbers that appear in the tool results or the supplied context.
Do not invent sensors, history, lactate thresholds, zones, or a changed training plan.
A recommendation is for the human coach to review. It is not applied.
If a value is missing, say it is missing.
Heart rate on repetitions shorter than 30 seconds is not evidence of how hard the effort was.
Earlier model interpretations are not measurements. Do not repeat one as a fact unless the stored activity data supports it.
"""

ATHLETE_SYSTEM = """You talk with one athlete about their own training.
Use only numbers that appear in the tool results or the supplied context.
Do not invent sensors, history, lactate thresholds, zones, race results, or a changed training plan.
If a value is missing, say it is missing.
Heart rate on repetitions shorter than 30 seconds is not evidence of how hard the effort was.
Earlier model interpretations are not measurements. Do not repeat one as a fact unless the stored activity data supports it.
"""

ATHLETE_PROMPT = """You are this athlete's training assistant.
Use the tools to read their intake, the coach's plan, recent runs, laps, calculated metrics, weekly mileage, and saved analyses before you answer.
Explain the week they ask about, how a workout was executed, how pace, heart rate, and workload are changing, and progress toward the saved race goal.
Write plain sentences to the athlete. Do not change the plan. Do not invent a workout, injury, pace, heart rate, lactate value, or race result.
When a saved analysis is present, you may use it as an earlier interpretation and say so. Measured pace, distance, and heart rate come from the activity tools.
"""

AGENT_PROMPT = """You are the coach's training agent for the saved roster.
Use the tools to read athletes, intake, plans, recent runs, laps, calculated metrics, weekly mileage, and saved analyses before you answer.
Give specific coaching advice the coach can review. Write plain sentences, not headings or tables. Do not change a plan, and do not invent a workout, injury, pace, or race result.
If the roster has one athlete, that is who the question is about. If a name matches more than one athlete, ask which one.
When a saved analysis is present, you may use it as an earlier interpretation and say so. Measured pace, distance, and heart rate come from the activity tools.
"""

REPORT_PROMPT = """You write an activity analysis for the coach who is reading it, about one athlete on the roster.
The reader is the coach, not the athlete. Use athlete_profile.display_name and refer to the athlete by that name. Do not address the athlete as "you". Do not write instructions the athlete would follow.
Be specific. Use the measurements in the context. Do not be generic or motivational. Do not use the words optimize, enhance, or maximize.
An easy run, a recovery run, and a workout all use the same sections. An easy run is still a full analysis, not a one-sentence note.

Use only numbers, history, goals, and thresholds present in the context. Do not invent splits, sensors, lactate thresholds, race results, heart-rate zones, or a fitness prediction.
If a heart-rate zone name is not in the context, give the heart rate in bpm and do not name a zone.
If planned_vs_actual is null, do not mention a planned distance, pace, or workout. Do not say a planned session was unavailable.
When planned_vs_actual is present, those mileage, repetition, pace, and recovery differences were already calculated. Do not recompute them. Use the calculated summary. A difference is not automatically poor execution. Say whether the stored objective was met only from that execution.
Mention another day, such as yesterday or tomorrow, only when that workout appears in the context. Do not invent the surrounding plan.
On a workout, when metrics.workout_breakdown.label is present, that label and each repetition's pace were already calculated from the recording. Describe the session as that structure and quote those paces. Do not average different repetition distances into one pace, and do not describe a different session. metrics.repetitions can split one repetition across an automatic lap, so it is not the workout structure. On an easy or recovery run, do not describe a repetition workout. If mile laps are stored, summarize them as a pace range in one sentence. Do not list every mile.
On a workout, when metrics.elevation_effect.available is true, quote the elevation note. Do not recompute grade and do not invent a hill. If a slower mile or repetition lines up with a calculated climb, say so. If elevation_effect.available is false, leave elevation out. On an easy or recovery run, leave the elevation note out.
Heart rate on repetitions shorter than 30 seconds is not evidence of how hard the effort was.
Phrase activity_classification from the stored workout type, using labels such as Easy Run, Recovery, Interval Training, Threshold, Long Run, Strides, Tempo, or Progression. Do not contradict the stored classification.
Set effort_level to Easy, Moderate, or Hard Effort from the recorded pace, heart rate, and workout structure. If that evidence is thin, choose the closest level.
athlete_profile, comparable_activities, and recent_training are saved profile fields or measurements. Refer to a race goal, an earlier performance, or a lactate threshold only when that field is present.
When athlete_profile.intake is present, quote a race time only when that race is listed.
prior_interpretations are earlier model text, not measurements. Do not treat an earlier conclusion as a fact.
Set goal_progress_status to on_track, building, or needs_attention only when the supplied measurements support it. Otherwise use insufficient_evidence.
Nothing in this report changes the training plan. Tell the coach what to review. Do not tell the athlete what to do.
How a run felt is the athlete's sensation, not a command. Write "Check that easy running still feels normal before keeping the faster work." Do not write "Keep easy running feeling normal."

Write:
- summary: one paragraph of 3 to 5 sentences for the coach. Name the athlete. Include distance, average pace, how it compared with the stored plan when one is present, heart rate when it is stored, and the pace range when laps are stored.
- training_impact: one paragraph of 2 to 3 sentences on what this recorded session does for this athlete, such as recovery, aerobic volume, or the quality the workout was for.
- fitness_indicators: one sentence on what the recording can and cannot tell the coach about fitness.
- what_went_well: 2 to 3 sentences about one recorded strength, each tied to a number in the context. State the observation. Do not praise the athlete in the second person.
- where_to_focus: 2 to 3 sentences telling the coach what to check or decide, each tied to a number in the context. If nothing is off, say what the coach should confirm before the next stored session.
- goal_progress: one sentence for the coach. If the goal or the comparable evidence is missing, say so.
"""

REPORT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "activity_classification": {"type": "string"},
        "effort_level": {"type": "string", "enum": ["Easy", "Moderate", "Hard Effort"]},
        "summary": {"type": "string"},
        "training_impact": {"type": "string"},
        "fitness_indicators": {"type": "string"},
        "what_went_well": {"type": "array", "items": {"type": "string"}},
        "where_to_focus": {"type": "array", "items": {"type": "string"}},
        "goal_progress_status": {
            "type": "string",
            "enum": ["on_track", "building", "needs_attention", "insufficient_evidence"],
        },
        "goal_progress": {"type": "string"},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "activity_classification",
        "effort_level",
        "summary",
        "training_impact",
        "fitness_indicators",
        "what_went_well",
        "where_to_focus",
        "goal_progress_status",
        "goal_progress",
        "missing_information",
    ],
}

REPORT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "workout_coaching_report",
        "strict": True,
        "schema": REPORT_JSON_SCHEMA,
    },
}


def _sentences(value: list[str]) -> list[str]:
    items = [item.strip() for item in value if item and item.strip()]
    if len(items) < 1 or len(items) > 4:
        raise ValueError("provide 1 to 4 sentences")
    return items


class WorkoutReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_classification: str
    effort_level: Literal["Easy", "Moderate", "Hard Effort"]
    summary: str
    training_impact: str
    fitness_indicators: str
    what_went_well: list[str]
    where_to_focus: list[str]
    goal_progress_status: Literal["on_track", "building", "needs_attention", "insufficient_evidence"]
    goal_progress: str
    missing_information: list[str]

    @field_validator(
        "activity_classification",
        "summary",
        "training_impact",
        "fitness_indicators",
        "goal_progress",
    )
    @classmethod
    def text_present(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("section is empty")
        return text

    @field_validator("what_went_well", "where_to_focus")
    @classmethod
    def sentence_list(cls, value: list[str]) -> list[str]:
        return _sentences(value)


def validate_report(payload: dict) -> dict:
    return WorkoutReport.model_validate(payload).model_dump()


EASY_SESSION_TYPES = {"easy", "recovery"}
WORKOUT_SESSION_TYPES = {"intervals", "threshold", "tempo", "marathon_pace", "strides", "progression", "race", "long_run"}


def session_kind(workout_type: str | None, report: dict | None = None) -> str:
    """Easy and recovery stay short. A stored workout type keeps the full review."""
    if workout_type in EASY_SESSION_TYPES:
        return "easy"
    if workout_type in WORKOUT_SESSION_TYPES:
        return "workout"
    if isinstance(report, dict):
        label = str(report.get("activity_classification") or "").strip().lower()
        if label in {"easy run", "easy", "recovery", "recovery run"}:
            return "easy"
    return "workout"


def present_report(
    report: dict | None,
    *,
    workout_type: str | None,
    distance_meters: float | None,
    average_speed_mps: float | None,
) -> dict | None:
    """Keep the written analysis. Mark easy runs so the dashboard can label them."""
    del distance_meters, average_speed_mps
    if not isinstance(report, dict):
        return None
    shown = dict(report)
    shown["analysis_kind"] = session_kind(workout_type, report)
    summary = shown.get("summary")
    if isinstance(summary, str):
        shown["summary"] = summary.strip()
    return shown


def openai_configured(settings: Settings) -> bool:
    return bool(settings.openai_api_key.strip())


def _lap_payload(lap: ActivityLap) -> dict:
    raw = lap.raw_lap or {}
    return {
        "lap_number": lap.lap_number,
        "distance_meters": lap.distance_meters,
        "duration_seconds": lap.duration_seconds,
        "average_speed_mps": lap.average_speed_mps,
        "average_heart_rate_bpm": lap.average_heart_rate_bpm,
        "max_heart_rate_bpm": lap.max_heart_rate_bpm,
        "average_cadence": lap.average_cadence_spm,
        "cadence_field": raw.get("cadence_field"),
        "intensity": raw.get("intensity"),
        "lap_trigger": raw.get("lap_trigger"),
    }


def _activity_brief(activity: Activity, classification: WorkoutClassification | None) -> dict:
    return {
        "garmin_activity_id": activity.garmin_activity_id,
        "name": activity.name,
        "start_time_local": activity.start_time_local,
        "activity_type_key": activity.activity_type_key,
        "distance_meters": activity.distance_meters,
        "duration_seconds": activity.duration_seconds,
        "average_speed_mps": activity.average_speed_mps,
        "average_heart_rate_bpm": activity.average_heart_rate_bpm,
        "average_pace_seconds_per_mile": pace_seconds_per_mile(activity.average_speed_mps),
        "elevation_gain_meters": activity.elevation_gain_meters,
        "elevation_loss_meters": activity.elevation_loss_meters,
        "workout_type": None if classification is None else classification.workout_type,
        "import_status": activity.import_status,
    }


def _zones(athlete: Athlete) -> tuple[list | None, list | None]:
    preferences = athlete.workout_preferences or {}
    pace = preferences.get("pace_zones") or None
    heart = preferences.get("heart_rate_zones") or None
    return pace, heart


def build_metrics(session: Session, athlete: Athlete, activity: Activity) -> dict:
    laps = session.scalars(
        select(ActivityLap).where(ActivityLap.activity_id == activity.id).order_by(ActivityLap.lap_number)
    ).all()
    samples = session.scalars(
        select(ActivitySample)
        .where(ActivitySample.activity_id == activity.id)
        .order_by(ActivitySample.elapsed_seconds)
    ).all()
    classification = session.scalar(
        select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id)
    )
    pace_zones, heart_zones = _zones(athlete)
    metrics = activity_metrics(
        [_lap_payload(lap) for lap in laps],
        [
            {
                "elapsed_seconds": sample.elapsed_seconds,
                "distance_meters": sample.distance_meters,
                "speed_mps": sample.speed_mps,
                "heart_rate_bpm": sample.heart_rate_bpm,
                "altitude_meters": sample.altitude_meters,
            }
            for sample in samples
        ],
        classification=None
        if classification is None
        else {"evidence": classification.evidence, "workout_type": classification.workout_type},
        pace_zones=pace_zones,
        heart_rate_zones=heart_zones,
        elevation_gain_meters=activity.elevation_gain_meters,
        elevation_loss_meters=activity.elevation_loss_meters,
    )
    return {
        "activity": _activity_brief(activity, classification),
        "classification": None
        if classification is None
        else {
            "workout_type": classification.workout_type,
            "confidence": classification.confidence,
            "source": classification.source,
            "uncertainty": classification.uncertainty,
            "evidence": classification.evidence,
        },
        "laps": [_lap_payload(lap) for lap in laps],
        "metrics": metrics,
        "fit_summary": activity.fit_summary,
    }


def _find_activity(session: Session, athlete_id: int, garmin_activity_id: int) -> Activity | None:
    return session.scalar(
        select(Activity).where(
            Activity.athlete_id == athlete_id,
            Activity.garmin_activity_id == garmin_activity_id,
        )
    )


def _roster_ids(athletes: list[Athlete]) -> list[int]:
    return [athlete.id for athlete in athletes] or [0]


def _pick_athlete(athletes: list[Athlete], arguments: dict) -> Athlete | dict:
    raw_id = arguments.get("athlete_id")
    name = str(arguments.get("athlete_name") or "").strip().lower()
    if raw_id not in (None, ""):
        try:
            athlete_id = int(raw_id)
        except (TypeError, ValueError):
            return {"error": "athlete_id must be an integer"}
        match = next((athlete for athlete in athletes if athlete.id == athlete_id), None)
        if match is None:
            return {"error": "Athlete is not on this roster"}
        return match
    if name:
        exact = [athlete for athlete in athletes if athlete.display_name.lower() == name]
        partial = [athlete for athlete in athletes if name in athlete.display_name.lower()]
        choices = exact or partial
        if len(choices) == 1:
            return choices[0]
        if not choices:
            return {"error": "No athlete on the roster matches that name", "athletes": [athlete.display_name for athlete in athletes]}
        return {"error": "More than one athlete matches that name", "athletes": [athlete.display_name for athlete in choices]}
    if len(athletes) == 1:
        return athletes[0]
    return {"error": "Name the athlete. The roster has more than one.", "athletes": [athlete.display_name for athlete in athletes]}


def _find_roster_activity(session: Session, athletes: list[Athlete], garmin_activity_id: int) -> Activity | None:
    return session.scalar(
        select(Activity).where(
            Activity.athlete_id.in_(_roster_ids(athletes)),
            Activity.garmin_activity_id == garmin_activity_id,
        )
    )


def _owner(athletes: list[Athlete], activity: Activity) -> Athlete | None:
    return next((athlete for athlete in athletes if athlete.id == activity.athlete_id), None)


def _named_brief(activity: Activity, classification: WorkoutClassification | None, athletes: list[Athlete]) -> dict:
    brief = _activity_brief(activity, classification)
    owner = _owner(athletes, activity)
    brief["athlete_id"] = activity.athlete_id
    brief["athlete_name"] = None if owner is None else owner.display_name
    return brief


def _analysis_note(session: Session, activity_id: int) -> str | None:
    row = session.scalar(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id == activity_id, WorkoutAnalysis.status == "ready")
        .order_by(WorkoutAnalysis.id.desc())
        .limit(1)
    )
    if row is None or not isinstance(row.report, dict):
        return None
    summary = row.report.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    return summary.strip()[:500]


def _garmin_argument(arguments: dict) -> int | None:
    try:
        return int(arguments["garmin_activity_id"])
    except (KeyError, TypeError, ValueError):
        return None


def run_tool(session: Session, athletes: list[Athlete], name: str, arguments: dict) -> dict:
    names = {athlete.id: athlete.display_name for athlete in athletes}
    if name == "list_athletes":
        goals = {
            goal.athlete_id: goal
            for goal in session.scalars(select(TrainingGoal).where(TrainingGoal.athlete_id.in_(_roster_ids(athletes)))).all()
        }
        return {
            "athletes": [
                {
                    "athlete_id": athlete.id,
                    "display_name": athlete.display_name,
                    "target_time": athlete.target_time,
                    "race_goal": None if goals.get(athlete.id) is None else goals[athlete.id].primary_race_goal,
                }
                for athlete in athletes
            ]
        }
    if name == "get_athlete":
        athlete = _pick_athlete(athletes, arguments)
        if isinstance(athlete, dict):
            return athlete
        goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
        return {
            "athlete_id": athlete.id,
            "display_name": athlete.display_name,
            "target_time": athlete.target_time,
            "coach_notes": athlete.coach_notes,
            "running_experience": athlete.running_experience,
            "typical_weekly_mileage": athlete.typical_weekly_mileage,
            "race_goal": None if goal is None else goal.primary_race_goal,
            "goal_race_date": None if goal is None or goal.goal_race_date is None else goal.goal_race_date.isoformat(),
            "intake": _intake_for_report(athlete),
        }
    if name == "get_training_history":
        athlete = _pick_athlete(athletes, arguments)
        if isinstance(athlete, dict):
            return athlete
        rows = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
        classifications = {
            row.activity_id: row.workout_type
            for row in session.scalars(
                select(WorkoutClassification).where(
                    WorkoutClassification.activity_id.in_([activity.id for activity in rows] or [0])
                )
            ).all()
        }
        history = training_history(rows, classifications, now=datetime.now(UTC))
        recent = sorted(
            [activity for activity in rows if activity.start_time_utc is not None],
            key=lambda activity: activity.start_time_utc,
            reverse=True,
        )[:8]
        class_rows = {
            row.activity_id: row
            for row in session.scalars(
                select(WorkoutClassification).where(
                    WorkoutClassification.activity_id.in_([activity.id for activity in recent] or [0])
                )
            ).all()
        }
        history["recent_activities"] = []
        for activity in recent:
            brief = _named_brief(activity, class_rows.get(activity.id), athletes)
            brief["analysis_summary"] = _analysis_note(session, activity.id)
            history["recent_activities"].append(brief)
        history["athlete_id"] = athlete.id
        history["athlete_name"] = athlete.display_name
        return history
    if name == "list_recent_activities":
        try:
            limit = int(arguments.get("limit") or 8)
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 12))
        chosen = _pick_athlete(athletes, arguments) if arguments.get("athlete_id") or arguments.get("athlete_name") or len(athletes) == 1 else None
        if isinstance(chosen, dict):
            return chosen
        athlete_ids = _roster_ids(athletes) if chosen is None else [chosen.id]
        rows = session.scalars(
            select(Activity)
            .where(Activity.athlete_id.in_(athlete_ids))
            .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc())
            .limit(limit)
        ).all()
        classifications = {
            row.activity_id: row
            for row in session.scalars(
                select(WorkoutClassification).where(
                    WorkoutClassification.activity_id.in_([activity.id for activity in rows] or [0])
                )
            ).all()
        }
        activities = []
        for row in rows:
            brief = _named_brief(row, classifications.get(row.id), athletes)
            brief["athlete_name"] = names.get(row.athlete_id)
            activities.append(brief)
        return {"activities": activities}
    if name == "list_planned_workouts":
        chosen = _pick_athlete(athletes, arguments) if arguments.get("athlete_id") or arguments.get("athlete_name") or len(athletes) == 1 else None
        if isinstance(chosen, dict):
            return chosen
        athlete_ids = _roster_ids(athletes) if chosen is None else [chosen.id]
        today = datetime.now(UTC).date()
        plans = session.scalars(
            select(ScheduledWorkout)
            .where(
                ScheduledWorkout.athlete_id.in_(athlete_ids),
                ScheduledWorkout.scheduled_date >= today - timedelta(days=14),
                ScheduledWorkout.scheduled_date < today + timedelta(days=21),
            )
            .order_by(ScheduledWorkout.scheduled_date, ScheduledWorkout.id)
        ).all()
        return {
            "workouts": [
                {
                    "athlete_id": plan.athlete_id,
                    "athlete_name": names.get(plan.athlete_id),
                    "scheduled_date": plan.scheduled_date.isoformat(),
                    "title": plan.title,
                    "workout_type": plan.workout_type,
                    "distance_miles": None if plan.distance_meters is None else round(plan.distance_meters / 1609.344, 2),
                    "repetitions": plan.repetitions,
                    "target_pace_seconds_per_mile": plan.target_pace_seconds_per_mile,
                }
                for plan in plans
            ]
        }
    garmin_id = _garmin_argument(arguments)
    if garmin_id is None:
        return {"error": "garmin_activity_id is required"}
    activity = _find_roster_activity(session, athletes, garmin_id)
    if activity is None:
        return {"error": "Activity not found"}
    owner = _owner(athletes, activity)
    if owner is None:
        return {"error": "Activity not found"}
    if name == "get_activity":
        payload = build_metrics(session, owner, activity)
        payload.pop("laps", None)
        payload["athlete_name"] = owner.display_name
        payload["analysis_summary"] = _analysis_note(session, activity.id)
        return payload
    if name == "get_laps":
        laps = session.scalars(
            select(ActivityLap).where(ActivityLap.activity_id == activity.id).order_by(ActivityLap.lap_number)
        ).all()
        return {"athlete_name": owner.display_name, "laps": [_lap_payload(lap) for lap in laps]}
    if name == "get_metrics":
        payload = build_metrics(session, owner, activity)
        return {
            "athlete_name": owner.display_name,
            "metrics": payload["metrics"],
            "classification": payload["classification"],
        }
    if name == "compare_similar":
        classification = session.scalar(
            select(WorkoutClassification).where(WorkoutClassification.activity_id == activity.id)
        )
        if classification is None:
            return {"matches": [], "reason": "This activity has no workout type yet."}
        others = session.scalars(
            select(WorkoutClassification)
            .where(
                WorkoutClassification.workout_type == classification.workout_type,
                WorkoutClassification.activity_id != activity.id,
            )
            .limit(8)
        ).all()
        matches = []
        for other in others:
            row = session.get(Activity, other.activity_id)
            if row is None or row.athlete_id != owner.id:
                continue
            matches.append(_activity_brief(row, other))
            if len(matches) == 5:
                break
        return {"workout_type": classification.workout_type, "matches": matches}
    return {"error": f"Unknown tool {name}"}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_athletes",
            "description": "List the coach's roster with each athlete's saved race goal and target time.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_athlete",
            "description": "Load one athlete's saved profile, intake, race goal, and coach notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_training_history",
            "description": "Load one athlete's recent mileage, workout counts, latest runs, and saved analysis summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_planned_workouts",
            "description": "List planned workouts from the past two weeks and the next three weeks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_activities",
            "description": "List the newest stored activities with distance, duration, workout type, and athlete name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "athlete_id": {"type": "integer"},
                    "athlete_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity",
            "description": "Load one activity summary, classification, and calculated metrics by Garmin activity id.",
            "parameters": {
                "type": "object",
                "properties": {"garmin_activity_id": {"type": "integer"}},
                "required": ["garmin_activity_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_laps",
            "description": "Load parsed laps for one Garmin activity id.",
            "parameters": {
                "type": "object",
                "properties": {"garmin_activity_id": {"type": "integer"}},
                "required": ["garmin_activity_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrics",
            "description": "Load calculated repetition, recovery, drift, and zone metrics for one Garmin activity id.",
            "parameters": {
                "type": "object",
                "properties": {"garmin_activity_id": {"type": "integer"}},
                "required": ["garmin_activity_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_similar",
            "description": "Find up to five earlier activities with the same stored workout type.",
            "parameters": {
                "type": "object",
                "properties": {"garmin_activity_id": {"type": "integer"}},
                "required": ["garmin_activity_id"],
                "additionalProperties": False,
            },
        },
    },
]


def _client(settings: Settings):
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key, timeout=120.0, max_retries=1)


def _completion(client, **kwargs):
    try:
        return client.chat.completions.create(**kwargs, extra_body={"reasoning_effort": "none"})
    except Exception:
        return client.chat.completions.create(**kwargs)


def _response_tools() -> list[dict]:
    converted = []
    for tool in TOOLS:
        function = tool["function"]
        converted.append(
            {
                "type": "function",
                "name": function["name"],
                "description": function["description"],
                "parameters": function["parameters"],
            }
        )
    return converted


def _measured_activity(session: Session, athlete: Athlete, activity: Activity, classification: WorkoutClassification | None) -> dict:
    payload = build_metrics(session, athlete, activity)
    brief = _activity_brief(activity, classification)
    return {
        "activity": brief,
        "metrics": {
            "repetitions": payload["metrics"].get("repetitions"),
            "recoveries": payload["metrics"].get("recoveries"),
            "heart_rate_drift": payload["metrics"].get("heart_rate_drift"),
        },
    }


_INTAKE_FOR_REPORT = (
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
    "anything_else",
    "recent_races",
)


def _intake_for_report(athlete: Athlete) -> dict | None:
    raw = athlete.intake if isinstance(athlete.intake, dict) else None
    if not raw:
        return None
    kept: dict = {}
    for key in _INTAKE_FOR_REPORT:
        value = raw.get(key)
        if value in (None, "", [], {}):
            continue
        kept[key] = value
    return kept or None


def build_report_context(session: Session, athlete: Athlete, activity: Activity) -> dict:
    current = build_metrics(session, athlete, activity)
    workout_type = current["activity"].get("workout_type")
    activities = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all())
    now = datetime.now(UTC)
    seven_count, _, seven_meters = window_stats(activities, now=now, days=7)
    twenty_eight_count, _, twenty_eight_meters = window_stats(activities, now=now, days=28)
    filters = [Activity.athlete_id == athlete.id, Activity.id != activity.id]
    if workout_type:
        filters.append(WorkoutClassification.workout_type == workout_type)
    query = (
        select(Activity, WorkoutClassification)
        .join(WorkoutClassification, WorkoutClassification.activity_id == Activity.id)
        .where(*filters)
        .order_by(Activity.start_time_utc.is_(None), Activity.start_time_utc.desc())
        .limit(5)
    )
    comparable = []
    compared_ids = []
    for earlier, classification in session.execute(query).all():
        compared_ids.append(earlier.id)
        comparable.append(_measured_activity(session, athlete, earlier, classification))
    prior_rows = []
    if compared_ids:
        prior_rows = list(
            session.scalars(
                select(WorkoutAnalysis)
                .where(WorkoutAnalysis.activity_id.in_(compared_ids))
                .order_by(WorkoutAnalysis.id.desc())
            ).all()
        )
    seen: set[int] = set()
    prior_interpretations = []
    activity_by_id = {row.id: row for row in activities}
    for row in prior_rows:
        if row.activity_id in seen or not row.report:
            continue
        seen.add(row.activity_id)
        source = activity_by_id.get(row.activity_id)
        report = row.report
        prior_interpretations.append(
            {
                "label": "prior_interpretation_not_a_measurement",
                "garmin_activity_id": None if source is None else source.garmin_activity_id,
                "start_time_local": None if source is None else source.start_time_local,
                "summary": report.get("summary") or report.get("coach_daily_summary"),
                "goal_progress": report.get("goal_progress"),
            }
        )
    earlier_report = session.scalar(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id == activity.id)
        .order_by(WorkoutAnalysis.id.desc())
        .limit(1)
    )
    if earlier_report is not None and earlier_report.report:
        prior_interpretations.insert(
            0,
            {
                "label": "prior_interpretation_not_a_measurement",
                "garmin_activity_id": activity.garmin_activity_id,
                "start_time_local": activity.start_time_local,
                "summary": earlier_report.report.get("summary") or earlier_report.report.get("coach_daily_summary"),
                "goal_progress": earlier_report.report.get("goal_progress"),
            },
        )
    goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete.id))
    thresholds = session.scalars(
        select(AthleteThreshold).where(AthleteThreshold.athlete_id == athlete.id).order_by(AthleteThreshold.name)
    ).all()
    return {
        "athlete_profile": {
            "display_name": athlete.display_name,
            "running_experience": athlete.running_experience,
            "typical_weekly_mileage": athlete.typical_weekly_mileage,
            "max_heart_rate_bpm": athlete.max_heart_rate_bpm,
            "primary_race_goal": None if goal is None else goal.primary_race_goal,
            "goal_race_date": None if goal is None or goal.goal_race_date is None else goal.goal_race_date.isoformat(),
            "target_time": athlete.target_time,
            "intake": _intake_for_report(athlete),
            "thresholds": [
                {
                    "name": row.name,
                    "pace_seconds_per_mile": row.pace_seconds_per_mile,
                    "heart_rate_bpm": row.heart_rate_bpm,
                }
                for row in thresholds
            ],
            "note": "Null fields were not saved. Do not estimate them.",
        },
        "current_activity": current,
        "recent_training": {
            "last_7_days_activity_count": seven_count,
            "last_7_days_distance_meters": seven_meters,
            "last_28_days_activity_count": twenty_eight_count,
            "last_28_days_distance_meters": twenty_eight_meters,
        },
        "comparable_activities": comparable,
        "comparable_match": "same_stored_workout_type" if workout_type else "recent_activities_because_this_workout_has_no_type",
        "prior_interpretations": prior_interpretations,
        "planned_vs_actual": _planned_vs_actual(session, athlete, activity),
    }


def _planned_vs_actual(session: Session, athlete: Athlete, activity: Activity) -> dict | None:
    from zoneinfo import ZoneInfo

    from app.models import Coach, SyncJob
    from app.services.adherence import load_plan_view

    coach = None if athlete.coach_id is None else session.get(Coach, athlete.coach_id)
    zone = ZoneInfo(coach.timezone if coach is not None and coach.timezone else "America/New_York")
    last_sync = session.scalar(
        select(SyncJob)
        .where(SyncJob.athlete_id == athlete.id, SyncJob.status == "succeeded")
        .order_by(SyncJob.finished_at.desc())
    )
    view = load_plan_view(
        session,
        athlete.id,
        today=datetime.now(zone).date(),
        last_sync_at=None if last_sync is None else last_sync.finished_at,
    )
    for workout in view["workouts"]:
        match = workout.get("match") or {}
        if match.get("garmin_activity_id") != activity.garmin_activity_id:
            continue
        return {
            "scheduled_date": workout["scheduled_date"],
            "title": workout["title"],
            "status": workout["status"],
            "execution": workout["execution"],
            "summary": workout["summary"],
            "comparison": workout["comparison"],
            "note": "Calculated by the application. Do not recompute these differences.",
        }
    return None


def generate_report(session: Session, settings: Settings, athlete: Athlete, activity: Activity) -> WorkoutAnalysis:
    if not openai_configured(settings):
        raise RuntimeError("openai_not_configured")
    context = build_report_context(session, athlete, activity)
    workout_type = (context.get("current_activity") or {}).get("activity", {}).get("workout_type")
    kind = session_kind(workout_type if isinstance(workout_type, str) else None)
    length_note = (
        "This stored session is an easy or recovery run. Write for the coach, using the athlete's name. Summarize mile laps as a range when they are stored, and do not turn the run into a repetition workout."
        if kind == "easy"
        else "This stored session is a workout. Write for the coach, using the athlete's name, and include the calculated structure and elevation when those fields are present."
    )
    client = _client(settings)
    messages = [
        {"role": "system", "content": REPORT_PROMPT},
        {
            "role": "user",
            "content": length_note + "\nWrite the coaching report from this context only:\n" + json.dumps(context, default=str),
        },
    ]
    report = None
    validation_error = "The model returned no report."
    for _attempt in range(2):
        completion = _completion(
            client,
            model=settings.openai_model,
            response_format=REPORT_RESPONSE_FORMAT,
            messages=messages,
        )
        text = completion.choices[0].message.content or ""
        try:
            report = validate_report(json.loads(text))
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            validation_error = str(exc)
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": "That JSON failed validation. Return a corrected object. " + validation_error,
                }
            )
    if report is None:
        raise RuntimeError(f"report_validation_failed: {validation_error}")
    report = present_report(
        report,
        workout_type=workout_type if isinstance(workout_type, str) else None,
        distance_meters=activity.distance_meters,
        average_speed_mps=activity.average_speed_mps,
    )
    now = datetime.now(UTC)
    row = WorkoutAnalysis(
        activity_id=activity.id,
        status="ready",
        model=settings.openai_model,
        report=report,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def chat(
    session: Session,
    settings: Settings,
    athlete: Athlete,
    *,
    message: str,
    conversation_id: int | None,
    garmin_activity_id: int | None,
    athletes: list[Athlete] | None = None,
    audience: str = "coach",
) -> tuple[AiConversation, list[AiMessage]]:
    if not openai_configured(settings):
        raise RuntimeError("openai_not_configured")
    roster = [athlete] if audience == "athlete" else (athletes or [athlete])
    now = datetime.now(UTC)
    conversation = None
    if conversation_id is not None:
        conversation = session.scalar(
            select(AiConversation).where(
                AiConversation.id == conversation_id,
                AiConversation.athlete_id.in_(_roster_ids(roster)),
            )
        )
    activity = None
    if garmin_activity_id is not None:
        activity = _find_roster_activity(session, roster, garmin_activity_id)
    if conversation is None:
        conversation = AiConversation(
            athlete_id=athlete.id,
            activity_id=None if activity is None else activity.id,
            title=message[:80],
            created_at=now,
        )
        session.add(conversation)
        session.flush()
    session.add(
        AiMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            created_at=now,
        )
    )
    session.flush()
    history = session.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conversation.id).order_by(AiMessage.id)
    ).all()
    if audience == "athlete":
        messages = [
            {"role": "system", "content": ATHLETE_SYSTEM},
            {"role": "system", "content": ATHLETE_PROMPT},
        ]
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": AGENT_PROMPT},
        ]
    if activity is not None:
        if audience == "athlete":
            activity_note = f"The athlete opened this chat from their activity {activity.garmin_activity_id}."
        else:
            owner = _owner(roster, activity)
            owner_name = owner.display_name if owner is not None else "an athlete"
            activity_note = f"The coach opened this chat from {owner_name}'s Garmin activity {activity.garmin_activity_id}."
        messages.append({"role": "system", "content": activity_note})
    for item in history:
        if item.role in {"user", "assistant"}:
            messages.append({"role": item.role, "content": item.content})
    client = _client(settings)
    instructions = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
    model_input: list[dict] = [
        {"role": item["role"], "content": item["content"]}
        for item in messages
        if item["role"] in {"user", "assistant"}
    ]
    trace: list[dict] = []
    reply = ""
    for _round in range(6):
        response = client.responses.create(
            model=settings.openai_model,
            instructions=instructions,
            input=model_input,
            tools=_response_tools(),
            reasoning={"effort": "low"},
            store=False,
        )
        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            reply = response.output_text or ""
            break
        model_input.extend(item.model_dump(exclude_none=True) for item in response.output)
        for call in calls:
            try:
                arguments = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            try:
                result = run_tool(session, roster, call.name, arguments)
            except Exception as exc:
                result = {"error": safe_error(exc)}
            trace.append({"name": call.name, "arguments": arguments})
            model_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, default=str),
                }
            )
    else:
        reply = reply or "I could not finish an answer from the stored activities."
    assistant = AiMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=reply,
        tool_trace={"calls": trace} if trace else None,
        created_at=datetime.now(UTC),
    )
    session.add(assistant)
    session.commit()
    stored = session.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conversation.id).order_by(AiMessage.id)
    ).all()
    return conversation, list(stored)


def safe_error(exc: Exception) -> str:
    return redact_secrets(str(exc))
