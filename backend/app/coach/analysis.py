"""Two-step coaching analysis. The analyst reads the workout. The coach places it in training.

The report the coach sees is one document. The analyst's notes are stored with it
and are not a second report.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT_VERSION = "2026-11-22-coach-v3"
REASONING_EFFORT = "high"

WORKOUT_RULES = {
    "hill_sprints": (
        "Hill sprints. Judge each effort's duration, the recorded climb and grade, and whether speed or power stayed consistent. "
        "Efforts around 10 to 20 seconds are acceleration practice, not a speed-endurance session. "
        "Use the effort paces, not the average pace of the whole activity, and say how those differ. "
        "These are short acceleration and force-production efforts. They support faster running as practice, not as a measure of race fitness. "
        "Heart rate does not measure these reps. Power spikes are not a power score; use the effort average when it exists."
    ),
    "strides": (
        "Strides. Judge the short flat efforts and the recovery between them. "
        "Do not call them hills unless the efforts climbed. Heart rate on reps under 30 seconds is not the intensity."
    ),
    "intervals": (
        "Track or road intervals. Judge each rep's pace and duration, whether speed held or faded, and the recorded recovery. "
        "Compare with the planned workout only when that plan is in the packet. "
        "A flat recording is not a hill session."
    ),
    "threshold": (
        "Threshold. Judge how long the faster work lasted, whether pace and heart rate stayed steady, and the recovery structure. "
        "Match a saved threshold pace only when one is stored. Otherwise say the threshold is not confirmed."
    ),
    "tempo": (
        "Tempo. Judge the sustained faster block against the slower running in the same session. "
        "Do not rename it threshold unless a saved threshold pace matches."
    ),
    "easy": (
        "Easy running. Judge whether pace and heart rate stayed appropriate and steady. "
        "Summarize mile pace as a range. Do not turn the run into intervals."
    ),
    "recovery": (
        "Recovery running. Judge whether the effort stayed easy. Keep the reading short. Do not invent a quality session."
    ),
    "long_run": (
        "Long run. Judge pacing across the run, any late change in effort, and a faster segment only when one was recorded. "
        "Call it marathon-specific only when the plan or a stored marathon-pace segment says so."
    ),
    "progression": (
        "Progression. Judge how the pace changed from the start to the finish and whether the faster finish stayed controlled. "
        "Do not describe it as intervals."
    ),
    "marathon_pace": (
        "Marathon-pace work. Judge how long the athlete held the stored marathon pace and whether it stayed stable. "
        "This is practice, not proof of race fitness."
    ),
    "unknown": (
        "The workout structure is unknown or ambiguous. Say which measurements are missing. Do not invent repetitions or a stimulus."
    ),
}


ANALYST_PROMPT = """You analyze one recorded running workout for a coach. You do not write the final review.
Use only the packet. Do not invent splits, a race result, a threshold, a training phase, or a plan.
The activity average pace is not the pace of the fast efforts when those efforts are listed separately.
Heart rate on efforts shorter than 30 seconds is not evidence of intensity or of recovery quality.
Instantaneous speed and power can spike. Prefer the effort averages.
For each claim, reason from the observation to what it means, why it matters, and what the coach should weigh. Do not print those labels.
Apply the workout rule below. Do not use a rule for a different workout type.
{rule}
"""

COACH_PROMPT = """You write the report the athlete will read. Address the athlete as "you" and "your". Do not use the athlete's name.
The analyst notes are an interpretation. Measured pace, distance, climb, and heart rate come from the detection packet.
Rank the findings in coaching_assessment.ranked_findings before you write the paragraphs. Order them by what they say about the execution, then by a stored goal, then by whether they should affect the next workout, then by how strong the evidence is. Keep at most four. The paragraphs use only the highest-value findings.
workout_analysis is one paragraph of about 40 to 60 words: what you accomplished, how well it was executed, and the performance difference that matters.
training_impact is one paragraph of about 25 to 40 words: the stimulus this session provided and why it matters for the training that is actually stored.
coach_takeaway is one paragraph of about 25 to 40 words: the conclusion, what to carry into the next session, and whether any change is warranted.
A quality session is 100 to 140 words across those three paragraphs. An easy or recovery run is 60 to 90 words. Stay under 180 words. Do not add a greeting or a closing line.
Put the fuller reading in coaching_assessment: execution_judgment, primary_stimulus, future_consideration, historical_context, and material_limitations. adjustment is continue, adjust, or insufficient_evidence.
Mention a recording limit in the paragraphs only when it changes the conclusion. A stimulus is not proof that an adaptation has occurred.
Do not invent a race time, a personal best, a training phase, a threshold, or a plan. When training_phase is null, do not name a phase. When no race goal is stored, do not judge progress toward one.
When same_day_activities lists another run, mention it once only if it changes the reading of this session. Do not fold it into this activity's average pace.
When detection.observed.signals.gps is true, do not say GPS is missing.
When planned_vs_actual is null, do not mention a planned target.
Do not recommend a recovery day unless the packet contains a fatigue measurement. Do not change the plan unless the recording justifies it.
Do not claim elite power, or that heart rate confirms recovery on short reps, or that this session proves race fitness.
Do not repeat one insight in more than one paragraph.
"""

ANALYST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detected_workout": {"type": "string"},
        "confidence_note": {"type": "string"},
        "primary_stimulus": {"type": "string"},
        "secondary_stimulus": {"type": "string"},
        "execution": {"type": "string"},
        "rep_notes": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "detected_workout",
        "confidence_note",
        "primary_stimulus",
        "secondary_stimulus",
        "execution",
        "rep_notes",
        "strengths",
        "limitations",
        "evidence",
        "uncertainty",
    ],
}

COACHING_ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ranked_findings": {"type": "array", "items": {"type": "string"}},
        "execution_judgment": {"type": "string"},
        "primary_stimulus": {"type": "string"},
        "future_consideration": {"type": "string"},
        "adjustment": {"type": "string", "enum": ["continue", "adjust", "insufficient_evidence"]},
        "material_limitations": {"type": "array", "items": {"type": "string"}},
        "historical_context": {"type": "string"},
    },
    "required": [
        "ranked_findings",
        "execution_judgment",
        "primary_stimulus",
        "future_consideration",
        "adjustment",
        "material_limitations",
        "historical_context",
    ],
}

COACH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "workout_analysis": {"type": "string"},
        "training_impact": {"type": "string"},
        "coach_takeaway": {"type": "string"},
        "coaching_assessment": COACHING_ASSESSMENT_SCHEMA,
    },
    "required": ["workout_analysis", "training_impact", "coach_takeaway", "coaching_assessment"],
}


class AnalystNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_workout: str
    confidence_note: str
    primary_stimulus: str
    secondary_stimulus: str
    execution: str
    rep_notes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


def workout_rule(workout_type: str | None) -> str:
    if not workout_type:
        return WORKOUT_RULES["unknown"]
    return WORKOUT_RULES.get(workout_type, WORKOUT_RULES["unknown"])


def detected_type(context: dict) -> tuple[str | None, float]:
    metrics = ((context.get("current_activity") or {}).get("metrics") or {})
    detection = (metrics.get("workout_intelligence") or {}).get("classification") or {}
    kind = detection.get("workout_type")
    confidence = detection.get("confidence")
    if not isinstance(kind, str):
        stored = ((context.get("current_activity") or {}).get("activity") or {}).get("workout_type")
        return stored if isinstance(stored, str) else None, 0.0
    return kind, float(confidence or 0)


def surrounding_sessions(
    rows: list[dict],
    *,
    activity_id: int,
    activity_day: str | None,
    anchor: datetime | None,
) -> dict:
    """Sessions before this activity, plus anything else on the same local day."""
    anchor_utc = _as_utc(anchor)
    cutoff = None if anchor_utc is None else anchor_utc - timedelta(days=14)
    recent = []
    same_day = []
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("id") == activity_id:
            continue
        started = _as_utc(row.get("start_time_utc"))
        local = str(row.get("start_time_local") or "")
        day = local[:10] if len(local) >= 10 else None
        on_day = activity_day is not None and day == activity_day
        before = anchor_utc is not None and started is not None and started < anchor_utc
        in_window = before and cutoff is not None and started >= cutoff
        if on_day:
            same_day.append(_session_brief(row))
        if in_window or (on_day and before):
            recent.append(_session_brief(row))
            label = str(row.get("workout_type") or "unclassified")
            counts[label] = counts.get(label, 0) + 1
    recent.sort(key=lambda item: item.get("start_time_local") or "")
    same_day.sort(key=lambda item: item.get("start_time_local") or "")
    return {
        "recent_sessions": recent[-12:],
        "same_day_activities": same_day,
        "workout_type_counts": counts,
    }


def guard_report(report: dict, context: dict) -> list[str]:
    """Flag claims the recording cannot support. The caller may ask the model to revise."""
    text = _report_text(report).lower()
    violations = []
    if _short_efforts(context) and re.search(r"heart rate (confirms|shows|proves)|hr confirms|excellent recovery", text):
        violations.append("Heart rate on efforts under 30 seconds was used as intensity or recovery evidence.")
    if re.search(r"elite (sprint |running )?power", text):
        violations.append("The report claims elite power. The recording cannot establish that.")
    if re.search(r"proves .{0,80}(mile|marathon|10k|fitness|ready)", text):
        violations.append("The report treats this session as proof of race fitness.")
    profile = context.get("athlete_profile") or {}
    goals_missing = not profile.get("primary_race_goal") and not (profile.get("intake") or {}).get("recent_races")
    if goals_missing and re.search(r"\d:\d{2}(?::\d{2})?\s+(marathon|mile|10k)", text):
        violations.append("The report cites a race time that is not stored for this athlete.")
    signals = (
        (((context.get("current_activity") or {}).get("metrics") or {}).get("workout_intelligence") or {}).get("observed") or {}
    ).get("signals") or {}
    if signals.get("gps") is True and re.search(r"\bgps\b.{0,40}(absent|missing|not stored|no gps)|no gps|coordinates were not", text):
        violations.append("The report says GPS is missing, but coordinates were stored.")
    visible = _visible_words(report)
    if visible is None:
        for key in ("summary", "execution_analysis", "training_impact", "coach_takeaway"):
            if not str(report.get(key) or "").strip():
                violations.append(f"{key} is empty")
        return violations
    if not re.search(r"\byou(?:r|rself)?\b", text):
        violations.append("The report does not address the athlete as you.")
    limit = 100 if _is_easy(context) else 180
    if visible > limit:
        violations.append(
            f"The athlete-facing report is {visible} words. Rewrite it under {limit} words and keep the main finding."
        )
    for key in ("workout_analysis", "training_impact", "coach_takeaway"):
        if not str(report.get(key) or "").strip():
            violations.append(f"{key} is empty")
    return violations


def score_report(report: dict, context: dict) -> dict:
    """Deterministic 1–5 review. A fluent report with a forbidden claim fails."""
    violations = guard_report(report, context)
    text = _report_text(report)
    lowered = text.lower()
    kind, confidence = detected_type(context)
    name = str((context.get("athlete_profile") or {}).get("display_name") or "")
    understanding = 2
    if kind and confidence >= 0.6 and kind.replace("_", " ") in lowered:
        understanding = 5
    elif kind and kind.replace("_", " ") in lowered:
        understanding = 4
    execution = 2
    efforts = _efforts(context)
    if efforts and any(_effort_mentioned(effort, lowered) for effort in efforts):
        execution = 5
    elif not efforts and "pace" in lowered:
        execution = 4
    physiological = 4 if "cannot" in lowered or "does not prove" in lowered or "not proof" in lowered else 3
    if violations:
        physiological = 1
    athlete = 4 if (name and name.lower() in lowered) or re.search(r"\byou(?:r)?\b", lowered) else 2
    if any("race time" in item or "elite power" in item for item in violations):
        athlete = 1
    history = 3
    same_day = context.get("same_day_activities") or []
    if same_day:
        history = 5 if any(_session_mentioned(session, lowered) for session in same_day) else 1
    elif not context.get("recent_sessions"):
        history = 3
    recommendations = 4 if str(report.get("coach_takeaway") or "").strip() else 1
    if "recovery day" in lowered and "fatigue" not in json.dumps(context.get("current_activity") or {}).lower():
        recommendations = 2
    evidence = 1 if violations else 5
    brief = [str(report.get(key) or "").strip() for key in ("workout_analysis", "training_impact", "coach_takeaway")]
    if "workout_analysis" in report or "coaching_assessment" in report:
        clarity = 5 if all(brief) and len(set(brief)) == 3 else 3
    else:
        sections = [
            str(report.get(key) or "")
            for key in ("summary", "execution_analysis", "training_impact", "fitness_indicators", "coach_takeaway")
        ]
        filled = [section for section in sections if section.strip()]
        clarity = 5 if len(filled) >= 4 and len(set(filled)) == len(filled) else 3
    scores = {
        "workout_understanding": understanding,
        "execution": execution,
        "physiological": physiological,
        "athlete_specific": athlete,
        "history": history,
        "recommendations": recommendations,
        "evidence": evidence,
        "clarity": clarity,
    }
    return {
        "scores": scores,
        "critical_failures": violations,
        "passed": not violations and min(scores.values()) >= 3,
    }


def run_coaching_analysis(settings, context: dict, complete) -> tuple[dict, dict]:
    """Ask the analyst, then the coach. Revise once if the guard rejects the report."""
    kind, _confidence = detected_type(context)
    rule = workout_rule(kind if _confidence >= 0.6 else "unknown")
    analyst_payload = complete(
        model=settings.gemini_model,
        reasoning_effort=REASONING_EFFORT,
        system=ANALYST_PROMPT.format(rule=rule),
        user="Analyze this recording:\n" + json.dumps(_analyst_packet(context), default=str),
        schema_name="workout_analyst_notes",
        schema=ANALYST_SCHEMA,
    )
    try:
        analyst = AnalystNotes.model_validate(analyst_payload).model_dump()
    except ValidationError as exc:
        logger.warning("Analyst notes failed validation: %s", exc.__class__.__name__)
        raise
    report = _coach_call(settings, context, analyst, complete, violations=None)
    violations = guard_report(report, context)
    if violations:
        logger.info("Coaching report failed the evidence guard: %s", "; ".join(violations))
        report = _coach_call(settings, context, analyst, complete, violations=violations)
        violations = guard_report(report, context)
    trace = {
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "model": settings.gemini_model,
        "reasoning_effort": REASONING_EFFORT,
        "workout_rule": kind,
        "analyst": analyst,
        "guard_violations": violations,
    }
    return report, trace


def _coach_call(settings, context: dict, analyst: dict, complete, violations: list[str] | None) -> dict:
    note = ""
    if violations:
        note = "Revise the report. The previous draft failed these checks: " + "; ".join(violations) + "\n"
    depth = (
        "Easy or recovery session. The three paragraphs together should be 60 to 90 words.\n"
        if _is_easy(context)
        else "Quality session. The three paragraphs together should be 100 to 140 words.\n"
    )
    return complete(
        model=settings.gemini_model,
        reasoning_effort=REASONING_EFFORT,
        system=COACH_PROMPT,
        user=depth + note + "Write the report from this packet only:\n" + json.dumps(_coach_packet(context, analyst), default=str),
        schema_name="workout_coaching_report",
        schema=COACH_SCHEMA,
    )


def _analyst_packet(context: dict) -> dict:
    current = context.get("current_activity") or {}
    metrics = current.get("metrics") or {}
    return {
        "athlete_name": (context.get("athlete_profile") or {}).get("display_name"),
        "activity": current.get("activity"),
        "detection": metrics.get("workout_intelligence"),
        "elevation_effect": metrics.get("elevation_effect"),
        "planned_vs_actual": context.get("planned_vs_actual"),
    }


def _coach_packet(context: dict, analyst: dict) -> dict:
    comparable = []
    for item in context.get("comparable_activities") or []:
        if isinstance(item, dict) and item.get("activity"):
            comparable.append(item["activity"])
    return {
        "analyst": analyst,
        "athlete_profile": context.get("athlete_profile"),
        "recent_training": context.get("recent_training"),
        "recent_sessions": context.get("recent_sessions"),
        "same_day_activities": context.get("same_day_activities"),
        "upcoming_workouts": context.get("upcoming_workouts"),
        "comparable_activities": comparable,
        "planned_vs_actual": context.get("planned_vs_actual"),
        "detection": ((context.get("current_activity") or {}).get("metrics") or {}).get("workout_intelligence"),
    }


def _session_brief(row: dict) -> dict:
    return {
        "garmin_activity_id": row.get("garmin_activity_id"),
        "name": row.get("name"),
        "start_time_local": row.get("start_time_local"),
        "distance_meters": row.get("distance_meters"),
        "duration_seconds": row.get("duration_seconds"),
        "average_speed_mps": row.get("average_speed_mps"),
        "workout_type": row.get("workout_type"),
    }


def _efforts(context: dict) -> list[dict]:
    detection = ((context.get("current_activity") or {}).get("metrics") or {}).get("workout_intelligence") or {}
    efforts = (detection.get("observed") or {}).get("efforts") or []
    return [effort for effort in efforts if isinstance(effort, dict)]


def _short_efforts(context: dict) -> bool:
    efforts = _efforts(context)
    return bool(efforts) and all(float(effort.get("duration_seconds") or 0) < 30 for effort in efforts)


def _is_easy(context: dict) -> bool:
    kind, confidence = detected_type(context)
    return confidence >= 0.6 and kind in {"easy", "recovery"}


def _effort_mentioned(effort: dict, lowered: str) -> bool:
    duration = effort.get("duration_seconds")
    distance = effort.get("distance_meters")
    checks = []
    if isinstance(duration, (int, float)):
        checks.append(str(int(round(duration))))
    if isinstance(distance, (int, float)):
        checks.append(str(int(round(distance))))
    return any(check and check in lowered for check in checks)


def _session_mentioned(session: dict, lowered: str) -> bool:
    distance = session.get("distance_meters")
    if not isinstance(distance, (int, float)):
        return False
    miles = distance / 1609.344
    kilometers = distance / 1000
    checks = (f"{miles:.0f}", f"{miles:.1f}", f"{kilometers:.0f}", f"{kilometers:.1f}")
    return any(check in lowered for check in checks)


def _visible_words(report: dict) -> int | None:
    if "workout_analysis" not in report and "coaching_assessment" not in report:
        return None
    parts = [str(report.get(key) or "").strip() for key in ("workout_analysis", "training_impact", "coach_takeaway")]
    return len(" ".join(parts).split())


def _report_text(report: dict) -> str:
    parts = []
    for key in (
        "activity_classification",
        "workout_identification",
        "workout_analysis",
        "summary",
        "execution_analysis",
        "training_impact",
        "fitness_indicators",
        "coach_takeaway",
        "goal_progress",
    ):
        value = report.get(key)
        if isinstance(value, str):
            parts.append(value)
    assessment = report.get("coaching_assessment")
    if isinstance(assessment, dict):
        for value in assessment.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value)
    for key in ("what_went_well", "where_to_focus", "missing_information"):
        value = report.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def _as_utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
