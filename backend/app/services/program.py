"""Turn an uploaded training program into scheduled workouts."""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta

from app.config import Settings
from app.garmin.mapping import METERS_PER_MILE
from app.services.adherence import calendar_plans, normalize_workout_type, parse_pace, parse_plan_csv, spreadsheet_text

PROGRAM_PROMPT = """You turn one written running program into scheduled workouts for a coach.
Use only sessions that are written in the program. Do not add a workout, a pace, a distance, or a rest day that the program does not state.
If the program gives a calendar date, use that date. Ignore the anchor date in that case.
If the program gives weekdays or week numbers and no calendar date, week 1 starts on the anchor date. Each later week starts seven days later. Place each session on its weekday.
Return dates as YYYY-MM-DD. Keep the workout title close to the program's wording.
workout_type must be one of: easy, recovery, long_run, intervals, threshold, tempo, marathon_pace, strides, progression, race, other. Use null when the program does not name a type.
distance_miles is the total distance when the program states one. Convert kilometers to miles. Use null when no distance is written.
Put extra instructions from the program in notes. Leave a field null when it is not written.
List any session you could not date in skipped. Do not invent a date for it.
"""

PLAN_REQUEST_PROMPT = """You are an experienced elite endurance coach. A coach has asked you to write a training plan. Write the sessions yourself.
A request such as "I want a plan for training for the mile" or "I want a plan for coach training for the mile" means author a mile plan. Do not wait for a document, and do not reply that no program was supplied.
The plan starts on the anchor date. Write six weeks. Put each session on a weekday. Include easy running, one longer run, strides or short hills, and event-specific work. Leave at least one easier day between hard sessions. Do not make every day hard.
For the mile, develop aerobic support, running economy and speed, and race-specific intensity around 800m to mile effort. Early weeks carry more easy running and strides. Later weeks add shorter, faster repetitions. The last week eases before a short race-pace session.
For another distance, use the same standard and match the work to that event. A 5K needs VO2max and threshold. A marathon needs more easy volume, a longer run, and marathon-pace work.
Use an athlete fact only when it is supplied. Do not invent a personal best, a threshold pace, a weekly mileage, or a weakness. When no pace is known, describe the effort in notes and leave target_pace null.
workout_type must be one of: easy, recovery, long_run, intervals, threshold, tempo, marathon_pace, strides, progression, race, other.
distance_miles is the total distance of the session you are prescribing.
repetitions and rep_distance_miles are only for the faster pieces you are prescribing. recovery_seconds is the rest between those pieces when you prescribe one.
Return dates as YYYY-MM-DD. Keep the title short, the way a coach would write it on a plan.
Put how the session should feel in notes. skipped stays empty.
"""

PROGRAM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "workouts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scheduled_date": {"type": "string"},
                    "title": {"type": "string"},
                    "workout_type": {"type": ["string", "null"]},
                    "distance_miles": {"type": ["number", "null"]},
                    "repetitions": {"type": ["integer", "null"]},
                    "rep_distance_miles": {"type": ["number", "null"]},
                    "recovery_seconds": {"type": ["number", "null"]},
                    "target_pace": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": [
                    "scheduled_date",
                    "title",
                    "workout_type",
                    "distance_miles",
                    "repetitions",
                    "rep_distance_miles",
                    "recovery_seconds",
                    "target_pace",
                    "notes",
                ],
            },
        },
        "skipped": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["workouts", "skipped"],
}


def _decode_text(payload: bytes) -> str:
    return payload.decode("utf-8-sig", errors="replace")


def program_text(filename: str, text: str | None, content_base64: str | None) -> tuple[str, bytes | None]:
    name = filename.lower()
    if not name.endswith((".csv", ".xlsx", ".txt", ".md", ".text")):
        raise ValueError("Upload a CSV, Excel, or plain text file.")
    raw = base64.b64decode(content_base64) if content_base64 else None
    if name.endswith(".xlsx"):
        if raw is None:
            raise ValueError("The spreadsheet could not be read.")
        return "", raw
    if raw is not None and not text:
        text = _decode_text(raw)
    if not text or not text.strip():
        raise ValueError("The file is empty.")
    return text[:20000], raw


def _structured(filename: str, text: str, raw: bytes | None, *, week_one: date | None = None, focus: date | None = None) -> tuple[list[dict], list[str], bool]:
    name = filename.lower()
    if name.endswith(".xlsx") and raw is not None:
        return calendar_plans(raw, focus=focus, week_one=week_one)
    if name.endswith(".csv"):
        plans, errors = parse_plan_csv(text, week_one=week_one)
        return plans, errors, False
    return [], [], False


def _stored_plan(item: dict) -> dict | None:
    title = str(item.get("title") or "").strip()
    raw_date = item.get("scheduled_date")
    if hasattr(raw_date, "isoformat") and not isinstance(raw_date, str):
        scheduled = raw_date
    else:
        try:
            scheduled = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            return None
    if not title or scheduled.year < 2020 or scheduled.year > date.today().year + 2:
        return None
    distance = item.get("distance_miles")
    if "distance_meters" in item:
        distance_meters = item.get("distance_meters")
    else:
        distance_meters = None if not isinstance(distance, (int, float)) else float(distance) * METERS_PER_MILE
    rep_distance = item.get("rep_distance_miles")
    if "rep_distance_meters" in item:
        rep_distance_meters = item.get("rep_distance_meters")
    else:
        rep_distance_meters = None if not isinstance(rep_distance, (int, float)) else float(rep_distance) * METERS_PER_MILE
    notes = item.get("notes") or item.get("coach_notes")
    note_text = notes.strip() if isinstance(notes, str) else ""
    pace_text = item.get("target_pace") if isinstance(item.get("target_pace"), str) else None
    pace = item.get("target_pace_seconds_per_mile")
    if pace is None:
        pace = parse_pace(pace_text)
    if pace is None and pace_text and pace_text.strip():
        note_text = f"{note_text}\nPace: {pace_text.strip()}".strip()
    repetitions = item.get("repetitions")
    stored = {
        "scheduled_date": scheduled,
        "title": title[:200],
        "workout_type": normalize_workout_type(item.get("workout_type") if isinstance(item.get("workout_type"), str) else None),
        "distance_meters": distance_meters,
        "repetitions": repetitions if isinstance(repetitions, int) else None,
        "rep_distance_meters": rep_distance_meters,
        "recovery_seconds": item.get("recovery_seconds") if isinstance(item.get("recovery_seconds"), (int, float)) else None,
        "target_pace_seconds_per_mile": pace,
        "coach_notes": note_text[:1000] or None,
    }
    for field in ("warmup", "cooldown", "intensity", "details"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            stored[field] = value.strip()[:4000 if field == "details" else 1000]
    if stored["title"].lower() in {"rest", "rest day", "off", "off day"} and stored["workout_type"] in {None, "other"}:
        stored["workout_type"] = "recovery"
    return stored


def _from_model(settings: Settings, text: str, *, today: date, start: date) -> tuple[list[dict], list[str]]:
    from app.coach.gemini import complete_messages, gemini_configured

    if not gemini_configured(settings):
        raise RuntimeError("gemini_not_configured")
    raw_text = complete_messages(
        settings,
        model=settings.gemini_model,
        messages=[
            {"role": "system", "content": PROGRAM_PROMPT},
            {
                "role": "user",
                "content": f"Today is {today.isoformat()}. The anchor date for an undated week 1 is {start.isoformat()}.\n\nProgram:\n{text}",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "training_program", "strict": True, "schema": PROGRAM_SCHEMA},
        },
    )
    try:
        payload = json.loads(raw_text or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("The program could not be read.") from exc
    plans = []
    skipped = [item for item in payload.get("skipped") or [] if isinstance(item, str) and item.strip()]
    for item in payload.get("workouts") or []:
        stored = _stored_plan(item)
        if stored is None:
            label = str(item.get("title") or "Untitled").strip() or "Untitled"
            skipped.append(f"{label} had no usable date.")
            continue
        plans.append(stored)
    return plans[:120], skipped[:40]


def workouts_from_request(
    settings: Settings,
    request: str,
    *,
    today: date,
    start: date,
    athlete_name: str | None = None,
    race_goal: str | None = None,
    target_time: str | None = None,
) -> tuple[list[dict], list[str], str]:
    from app.coach.gemini import complete_messages, gemini_configured

    ask = request.strip()
    if len(ask) < 8:
        raise ValueError("Describe the plan you want.")
    if not gemini_configured(settings):
        raise RuntimeError("gemini_not_configured")
    facts = [f"Athlete: {athlete_name or 'Athlete'}"]
    if race_goal:
        facts.append(f"Saved race goal: {race_goal}")
    if target_time:
        facts.append(f"Saved target time: {target_time}")
    raw_text = complete_messages(
        settings,
        model=settings.gemini_model,
        messages=[
            {"role": "system", "content": PLAN_REQUEST_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Today is {today.isoformat()}. The anchor date is {start.isoformat()}.\n"
                    + "\n".join(facts)
                    + f"\n\nCoach request:\n{ask[:4000]}"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "training_program", "strict": True, "schema": PROGRAM_SCHEMA},
        },
    )
    try:
        payload = json.loads(raw_text or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("The plan could not be written.") from exc
    plans = []
    skipped = [item for item in payload.get("skipped") or [] if isinstance(item, str) and item.strip()]
    for item in payload.get("workouts") or []:
        stored = _stored_plan(item)
        if stored is None:
            label = str(item.get("title") or "Untitled").strip() or "Untitled"
            skipped.append(f"{label} had no usable date.")
            continue
        plans.append(stored)
    return plans[:120], skipped[:40], "generated"


def workouts_from_program(
    settings: Settings,
    filename: str,
    text: str | None,
    content_base64: str | None,
    *,
    today: date,
    start: date,
) -> tuple[list[dict], list[str], str]:
    body, raw = program_text(filename, text, content_base64)
    structured, errors, absolute = _structured(filename, body, raw, week_one=start, focus=today)
    if structured:
        plans = []
        for item in structured:
            stored = _stored_plan(item)
            if stored is not None:
                plans.append(stored)
        if plans:
            if not absolute:
                _place_on_start(plans, start)
            return plans[:400], errors[:40], "spreadsheet-dated" if absolute else "spreadsheet"
    if filename.lower().endswith(".xlsx"):
        body = spreadsheet_text(raw or b"")
    body = body.strip()[:20000]
    if not body:
        raise ValueError("The file is empty.")
    plans, skipped = _from_model(settings, body, today=today, start=start)
    return plans, skipped, "agent"


def _place_on_start(plans: list[dict], start: date) -> None:
    earliest = min(item["scheduled_date"] for item in plans)
    shift = start - earliest
    if shift == timedelta(0):
        return
    for item in plans:
        item["scheduled_date"] = item["scheduled_date"] + shift


def next_monday(today: date) -> date:
    return today + timedelta(days=(7 - today.weekday()) % 7)
