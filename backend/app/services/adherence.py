"""Planned-versus-actual comparisons. Differences are calculated here, not by the model."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from zipfile import ZipFile
from xml.etree import ElementTree

from app.garmin.mapping import METERS_PER_MILE, pace_seconds_per_mile

QUALITY_TYPES = {"intervals", "threshold", "tempo", "marathon_pace", "strides"}
RELATED_QUALITY = {"tempo", "threshold", "marathon_pace"}
EASY_TYPES = {"easy", "recovery"}
WORKOUT_TYPES = {
    "easy",
    "recovery",
    "long_run",
    "intervals",
    "threshold",
    "tempo",
    "marathon_pace",
    "strides",
    "progression",
    "race",
    "other",
}
TYPE_ALIASES = {
    "easy run": "easy",
    "recovery run": "recovery",
    "long": "long_run",
    "long run": "long_run",
    "interval": "intervals",
    "intervals": "intervals",
    "repetitions": "intervals",
    "reps": "intervals",
    "threshold": "threshold",
    "tempo": "tempo",
    "marathon pace": "marathon_pace",
    "mp": "marathon_pace",
    "strides": "strides",
    "stride": "strides",
    "progression": "progression",
    "race": "race",
}
_DAY_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
_TITLE_KEYS = ("title", "workout", "name", "session", "prescription", "description")
_DATE_KEYS = {"date", "scheduled_date", "week_of", "week_start", "start", "start_date"}
_WEEK_KEYS = ("week", "week_number", "week_num")
_BLANK_CELLS = {"-", "—", "–", "n/a", "na", "none", "."}


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def normalize_workout_type(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower().replace("_", " ")
    if not text:
        return None
    aliased = TYPE_ALIASES.get(text, text.replace(" ", "_"))
    return aliased if aliased in WORKOUT_TYPES else None


def parse_pace(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().lower().replace("/mi", "").replace("per mile", "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    match = re.fullmatch(r"(\d+):(\d{1,2})", text)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def format_pace(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    rounded = round(seconds)
    return f"{rounded // 60}:{rounded % 60:02d}"


def miles_from_meters(meters: float | None) -> float | None:
    if meters is None:
        return None
    return meters / METERS_PER_MILE


def _local_day(activity) -> date | None:
    local = getattr(activity, "start_time_local", None)
    if isinstance(local, str) and len(local) >= 10:
        try:
            return date.fromisoformat(local[:10])
        except ValueError:
            return None
    return None


def _hard_conflict(planned: str | None, actual: str | None) -> bool:
    if planned is None or actual is None or actual == "other" or planned == actual:
        return False
    if planned in QUALITY_TYPES and actual in EASY_TYPES | {"long_run"}:
        return True
    if planned in EASY_TYPES and actual in QUALITY_TYPES:
        return True
    if planned == "long_run" and actual in QUALITY_TYPES:
        return True
    if actual == "long_run" and planned in QUALITY_TYPES:
        return True
    return False


def _compatible(planned: str | None, actual: str | None) -> bool:
    if planned is None or actual is None:
        return False
    if planned == actual:
        return True
    return planned in RELATED_QUALITY and actual in RELATED_QUALITY


def match_score(plan, activity, actual_type: str | None) -> int | None:
    if _hard_conflict(plan.workout_type, actual_type):
        return None
    score = 10
    if plan.workout_type is None or actual_type is None:
        score += 10
    elif plan.workout_type == actual_type:
        score += 40
    elif _compatible(plan.workout_type, actual_type):
        score += 25
    planned = plan.distance_meters
    actual = activity.distance_meters
    if isinstance(planned, (int, float)) and planned > 0 and isinstance(actual, (int, float)):
        gap = abs(actual - planned) / planned
        if gap <= 0.10:
            score += 30
        elif gap <= 0.20:
            score += 15
    return score


def assign_matches(plans: list, activities: list, types: dict[int, str | None]) -> dict[int, object]:
    """Return plan id -> activity. A manual match is kept. One activity is used once."""
    by_id = {activity.id: activity for activity in activities}
    used: set[int] = set()
    assigned: dict[int, object] = {}
    for plan in plans:
        if getattr(plan, "match_source", None) == "confirmed_missed":
            continue
        if getattr(plan, "match_source", None) == "manual" and plan.match_activity_id in by_id:
            activity = by_id[plan.match_activity_id]
            assigned[plan.id] = activity
            used.add(activity.id)
    pairs = []
    for plan in plans:
        if plan.id in assigned or getattr(plan, "match_source", None) == "confirmed_missed":
            continue
        for activity in activities:
            if _local_day(activity) != plan.scheduled_date or activity.id in used:
                continue
            score = match_score(plan, activity, types.get(activity.id))
            if score is None:
                continue
            pairs.append((score, plan.id, activity.id))
    pairs.sort(key=lambda item: item[0], reverse=True)
    claimed_plans: set[int] = set()
    for score, plan_id, activity_id in pairs:
        if score < 20 or plan_id in claimed_plans or activity_id in used:
            continue
        assigned[plan_id] = by_id[activity_id]
        claimed_plans.add(plan_id)
        used.add(activity_id)
    return assigned


def sync_covers_date(*, scheduled: date, later_activity: bool, last_sync_at: datetime | None) -> bool:
    if later_activity:
        return True
    if last_sync_at is None:
        return False
    return last_sync_at.date() > scheduled


def compare_execution(
    plan,
    activity,
    *,
    actual_type: str | None,
    repetition_count: int | None,
    repetition_pace: float | None,
    repetition_distance_meters: float | None,
    recovery_seconds: float | None,
    recorded_effort: str | None,
) -> dict:
    planned_miles = miles_from_meters(plan.distance_meters)
    actual_miles = None if activity is None else miles_from_meters(activity.distance_meters)
    distance_difference = None
    distance_percent = None
    if planned_miles is not None and actual_miles is not None:
        distance_difference = actual_miles - planned_miles
        if planned_miles > 0:
            distance_percent = distance_difference / planned_miles * 100
    actual_pace = repetition_pace
    if actual_pace is None and activity is not None:
        actual_pace = pace_seconds_per_mile(activity.average_speed_mps)
    pace_difference = None
    if plan.target_pace_seconds_per_mile is not None and actual_pace is not None:
        pace_difference = actual_pace - plan.target_pace_seconds_per_mile
    effort = _comparable_effort(plan.intensity, recorded_effort)
    signals = []
    if plan.repetitions is not None and repetition_count is not None:
        signals.append(repetition_count >= plan.repetitions)
    if pace_difference is not None:
        signals.append(abs(pace_difference) <= 10)
    if distance_percent is not None:
        signals.append(abs(distance_percent) <= 10 or abs(distance_difference or 0) < 0.25)
    if plan.workout_type and actual_type and actual_type != "other":
        signals.append(plan.workout_type == actual_type or _compatible(plan.workout_type, actual_type))
    if plan.recovery_seconds is not None and recovery_seconds is not None:
        signals.append(abs(recovery_seconds - plan.recovery_seconds) < 30)
    if effort is not None:
        signals.append(effort["matches"])
    if not signals:
        execution = "insufficient_evidence"
    elif all(signals):
        execution = "met"
    else:
        execution = "partial"
    comparison = {
        "planned_distance_miles": planned_miles,
        "actual_distance_miles": actual_miles,
        "distance_difference_miles": distance_difference,
        "distance_difference_percent": distance_percent,
        "planned_pace_seconds_per_mile": plan.target_pace_seconds_per_mile,
        "actual_pace_seconds_per_mile": actual_pace,
        "pace_difference_seconds_per_mile": pace_difference,
        "planned_repetitions": plan.repetitions,
        "actual_repetitions": repetition_count,
        "planned_rep_distance_miles": miles_from_meters(plan.rep_distance_meters),
        "actual_rep_distance_miles": miles_from_meters(repetition_distance_meters),
        "planned_recovery_seconds": plan.recovery_seconds,
        "actual_recovery_seconds": recovery_seconds,
        "planned_workout_type": plan.workout_type,
        "actual_workout_type": actual_type,
        "planned_intensity": plan.intensity,
        "recorded_effort": None if effort is None else recorded_effort,
        "execution": execution,
    }
    comparison["summary"] = _summary(comparison)
    return comparison


def _comparable_effort(planned: str | None, recorded: str | None) -> dict | None:
    if not planned or not recorded:
        return None
    text = planned.strip().lower()
    recorded_level = {"easy": "easy", "moderate": "moderate", "hard effort": "hard", "hard": "hard"}.get(recorded.strip().lower())
    planned_level = None
    if text in {"easy", "easy effort"}:
        planned_level = "easy"
    elif text in {"moderate", "moderate effort"}:
        planned_level = "moderate"
    elif text in {"hard", "hard effort"}:
        planned_level = "hard"
    if planned_level is None or recorded_level is None:
        return None
    return {"matches": planned_level == recorded_level}


def _summary(comparison: dict) -> str | None:
    parts = []
    planned_reps = comparison["planned_repetitions"]
    actual_reps = comparison["actual_repetitions"]
    if planned_reps is not None and actual_reps is not None:
        parts.append(f"Completed {actual_reps} of {planned_reps} repetitions")
    pace_difference = comparison["pace_difference_seconds_per_mile"]
    if pace_difference is not None:
        rounded = round(pace_difference)
        if rounded == 0:
            pace_text = "at the prescribed pace"
        elif rounded > 0:
            pace_text = f"{rounded} seconds per mile slower than prescribed"
        else:
            pace_text = f"{abs(rounded)} seconds per mile faster than prescribed"
        if parts and planned_reps is not None:
            parts[-1] = f"{parts[-1]}, averaging {pace_text}"
        else:
            parts.append(f"Pace was {pace_text}")
    planned_miles = comparison["planned_distance_miles"]
    actual_miles = comparison["actual_distance_miles"]
    if planned_miles is not None and actual_miles is not None and planned_reps is None:
        parts.append(f"Ran {actual_miles:.2f} miles against {planned_miles:.2f} miles prescribed")
    planned_recovery = comparison["planned_recovery_seconds"]
    actual_recovery = comparison["actual_recovery_seconds"]
    if planned_recovery is not None and actual_recovery is not None and abs(actual_recovery - planned_recovery) >= 15:
        parts.append(f"Recovery averaged {round(actual_recovery)} seconds against {round(planned_recovery)} seconds prescribed")
    planned_type = comparison["planned_workout_type"]
    actual_type = comparison["actual_workout_type"]
    if planned_type and actual_type and planned_type != actual_type and not _compatible(planned_type, actual_type):
        parts.append(f"Stored workout type is {actual_type.replace('_', ' ')}; the plan prescribed {planned_type.replace('_', ' ')}")
    if not parts:
        return None
    return " ".join(part if part.endswith(".") else f"{part}." for part in parts)


def workout_status(plan, activity, comparison: dict | None, *, today: date, covered: bool, same_day_unmatched: bool) -> str:
    if getattr(plan, "match_source", None) == "confirmed_missed":
        return "confirmed_missed"
    if activity is not None and comparison is not None and comparison["execution"] == "partial":
        return "partially_completed"
    if activity is not None:
        return "completed"
    if plan.scheduled_date >= today:
        return "scheduled"
    if not covered:
        return "unmatched"
    if same_day_unmatched:
        return "unmatched"
    return "confirmed_missed"


def build_weeks(plans: list, activities: list, assigned: dict[int, object], statuses: dict[int, str], *, today: date) -> list[dict]:
    if not plans:
        return []
    starts = {week_start(plan.scheduled_date) for plan in plans}
    first, last = min(starts), max(starts)
    cursor = first
    weeks = []
    while cursor <= last:
        week_end = cursor + timedelta(days=7)
        week_plans = [plan for plan in plans if cursor <= plan.scheduled_date < week_end]
        week_activities = [activity for activity in activities if (day := _local_day(activity)) is not None and cursor <= day < week_end]
        known = [plan.distance_meters for plan in week_plans if plan.distance_meters is not None]
        planned_complete = bool(week_plans) and len(known) == len(week_plans)
        planned_miles = None if not known else sum(known) / METERS_PER_MILE
        actual_known = [activity.distance_meters for activity in week_activities if activity.distance_meters is not None]
        actual_miles = None if not actual_known else sum(actual_known) / METERS_PER_MILE
        variance_miles = None
        variance_percent = None
        if planned_complete and planned_miles and actual_miles is not None:
            variance_miles = actual_miles - planned_miles
            variance_percent = variance_miles / planned_miles * 100
        remaining = [
            plan.distance_meters / METERS_PER_MILE
            for plan in week_plans
            if plan.scheduled_date >= today and plan.distance_meters is not None and statuses.get(plan.id) == "scheduled"
        ]
        quality = [plan for plan in week_plans if plan.workout_type in QUALITY_TYPES]
        long_plans = [plan for plan in week_plans if plan.workout_type == "long_run" and plan.distance_meters is not None]
        long_actual = [
            assigned[plan.id].distance_meters
            for plan in week_plans
            if plan.workout_type == "long_run" and plan.id in assigned and assigned[plan.id].distance_meters is not None
        ]
        def count(status: str, selected=None) -> int:
            chosen = week_plans if selected is None else selected
            return sum(1 for plan in chosen if statuses.get(plan.id) == status)

        planned_count = len(week_plans)
        completed = count("completed")
        weeks.append(
            {
                "week_start": cursor.isoformat(),
                "in_progress": cursor <= today < week_end,
                "planned_miles": planned_miles,
                "planned_miles_complete": planned_complete,
                "actual_miles": actual_miles,
                "variance_miles": variance_miles,
                "variance_percent": variance_percent,
                "remaining_planned_miles": None if not remaining else sum(remaining),
                "planned_workouts": planned_count,
                "completed_workouts": completed,
                "partial_workouts": count("partially_completed"),
                "still_scheduled": count("scheduled"),
                "confirmed_missed": count("confirmed_missed"),
                "unmatched": count("unmatched"),
                "planned_quality": len(quality),
                "completed_quality": count("completed", quality),
                "partial_quality": count("partially_completed", quality),
                "planned_long_run_miles": None if not long_plans else sum(plan.distance_meters for plan in long_plans) / METERS_PER_MILE,
                "actual_long_run_miles": None if not long_actual else sum(long_actual) / METERS_PER_MILE,
                "adherence": None if planned_count == 0 else completed / planned_count,
            }
        )
        cursor = week_end
    return weeks


def adherence_trend(weeks: list[dict]) -> str | None:
    closed = [week for week in weeks if not week["in_progress"] and week["planned_workouts"]]
    if not closed:
        return None
    met = [
        week
        for week in closed
        if week["adherence"] is not None and week["adherence"] >= 0.85 and week["partial_workouts"] == 0 and week["confirmed_missed"] == 0
    ]
    return f"{len(met)} of {len(closed)} completed weeks met the prescribed workouts."


def current_week_flags(weeks: list[dict], workouts: list[dict], *, today: date) -> list[dict]:
    notes = []
    cutoff = week_start(today) - timedelta(days=7)
    current = next((week for week in weeks if week["in_progress"]), None)
    if current and current["planned_miles_complete"] and current["planned_miles"] and current["variance_percent"] is not None:
        remaining = current["remaining_planned_miles"] or 0
        actual = current["actual_miles"] or 0
        if current["still_scheduled"] == 0 and current["variance_percent"] <= -15:
            notes.append({"kind": "shortfall", "note": f"Mileage is {abs(current['variance_miles']):.1f} miles under the prescribed {current['planned_miles']:.1f} miles."})
        elif actual + remaining < current["planned_miles"] * 0.85:
            notes.append({"kind": "shortfall", "note": f"Completed mileage plus the distance still scheduled is under 85% of the prescribed {current['planned_miles']:.1f} miles."})
    for workout in workouts:
        if workout["workout_type"] not in QUALITY_TYPES and workout["workout_type"] != "long_run":
            continue
        if date.fromisoformat(workout["scheduled_date"]) < cutoff:
            continue
        if workout["status"] == "confirmed_missed":
            notes.append({"kind": "missed", "note": f"{workout['scheduled_date']} {workout['title']} was confirmed missed.", "garmin_activity_id": None})
        elif workout["status"] == "partially_completed" and workout.get("summary"):
            notes.append({"kind": "partial", "note": workout["summary"], "garmin_activity_id": (workout.get("match") or {}).get("garmin_activity_id")})
    closed = [week for week in weeks if not week["in_progress"] and week["planned_workouts"]]
    if closed and closed[-1]["adherence"] == 1 and closed[-1]["partial_workouts"] == 0:
        notes.append({"kind": "consistent", "note": "The last completed week matched the prescribed workouts."})
    if current and current["still_scheduled"] and current["planned_workouts"]:
        notes.append({"kind": "progress", "note": f"{current['completed_workouts']} of {current['planned_workouts']} prescribed workouts are completed so far; {current['still_scheduled']} remain scheduled."})
    return notes


def key_workout_status(workouts: list[dict], week: dict | None) -> str | None:
    if week is None:
        return None
    start = date.fromisoformat(week["week_start"])
    selected = [
        workout
        for workout in workouts
        if workout["workout_type"] in QUALITY_TYPES | {"long_run"} and start <= date.fromisoformat(workout["scheduled_date"]) < start + timedelta(days=7)
    ]
    if not selected:
        return None
    order = ["confirmed_missed", "partially_completed", "unmatched", "scheduled", "completed"]
    statuses = {workout["status"] for workout in selected}
    for status in order:
        if status in statuses:
            return status
    return None


def parse_plan_csv(text: str, *, week_one: date | None = None) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["The file has no header row."]
    return _rows_to_plans(list(reader), week_one=week_one)


def spreadsheet_text(payload: bytes) -> str:
    grid = _xlsx_grid(payload)
    lines = ["\t".join(cell.strip() for cell in row) for row in grid if any(cell.strip() for cell in row)]
    return "\n".join(lines)


def _xlsx_grid(payload: bytes) -> list[list[str]]:
    try:
        with ZipFile(io.BytesIO(payload)) as workbook:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for item in root.findall("m:si", namespace):
                    shared.append("".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
            sheet_name = next((name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")), None)
            if sheet_name is None:
                raise ValueError("The spreadsheet has no worksheet.")
            sheet = ElementTree.fromstring(workbook.read(sheet_name))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The spreadsheet could not be read. Save it as CSV if this file stays unreadable.") from exc
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    grid: list[list[str]] = []
    for row in sheet.findall("m:sheetData/m:row", namespace):
        values: list[str] = []
        for cell in row.findall("m:c", namespace):
            ref = cell.attrib.get("r", "")
            column = re.match(r"[A-Z]+", ref)
            index = _column_index(column.group(0)) if column else len(values)
            while len(values) < index:
                values.append("")
            raw = cell.find("m:v", namespace)
            text = "" if raw is None or raw.text is None else raw.text
            if cell.attrib.get("t") == "s" and text.isdigit():
                text = shared[int(text)] if int(text) < len(shared) else text
            values.append(text)
        grid.append(values)
    if not grid:
        raise ValueError("The spreadsheet has no rows.")
    return grid


_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_SHEET_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_SHEET_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def parse_plan_xlsx(payload: bytes, *, week_one: date | None = None) -> tuple[list[dict], list[str]]:
    plans, errors, _absolute = calendar_plans(payload, focus=None, week_one=week_one)
    return plans, errors


def calendar_plans(payload: bytes, *, focus: date | None, week_one: date | None = None) -> tuple[list[dict], list[str], bool]:
    """Read a workbook. A month tab that contains focus keeps its own dates."""
    try:
        sheets = _xlsx_sheets(payload)
    except ValueError as exc:
        return [], [str(exc)], False
    blocks: list[tuple[list[dict], list[str]]] = []
    other: list[dict] = []
    for sheet in sheets:
        block, block_errors, matched = _mileage_block_plans(sheet)
        if matched:
            if block:
                blocks.append((block, block_errors))
            continue
        grid = _sheet_rows(sheet)
        if not grid:
            continue
        header_index = 0
        while header_index < len(grid) and not any(cell.strip() for cell in grid[header_index]):
            header_index += 1
        if header_index >= len(grid):
            continue
        sheet_plans, sheet_errors = _grid_plans(grid[header_index:], week_one=week_one)
        if sheet_plans:
            other.append({"plans": sheet_plans, "errors": sheet_errors})
    if blocks:
        chosen, absolute = _current_block(blocks, focus)
        return chosen[0], chosen[1], absolute
    plans: list[dict] = []
    errors: list[str] = []
    for item in other:
        plans.extend(item["plans"])
        errors.extend(item["errors"])
    return plans, errors, False


def _current_block(blocks: list[tuple[list[dict], list[str]]], focus: date | None) -> tuple[tuple[list[dict], list[str]], bool]:
    if focus is not None:
        covering = []
        for plans, errors in blocks:
            start = min(plan["scheduled_date"] for plan in plans)
            end = max(plan["scheduled_date"] for plan in plans)
            if start <= focus <= end + timedelta(days=6):
                covering.append((plans, errors, start))
        if covering:
            plans, errors, _start = max(covering, key=lambda item: item[2])
            return (plans, errors), True
    if len(blocks) == 1:
        return blocks[0], False
    return max(blocks, key=lambda item: max(plan["scheduled_date"] for plan in item[0])), True


def _grid_plans(grid: list[list[str]], *, week_one: date | None) -> tuple[list[dict], list[str]]:
    headers = [value.strip() for value in grid[0]]
    records = []
    for values in grid[1:]:
        if not any(value.strip() for value in values):
            continue
        records.append({headers[index]: values[index] if index < len(values) else "" for index in range(len(headers))})
    return _rows_to_plans(records, week_one=week_one)


def _xlsx_sheets(payload: bytes) -> list[dict]:
    try:
        with ZipFile(io.BytesIO(payload)) as workbook:
            shared = _shared_strings(workbook)
            if "xl/workbook.xml" not in workbook.namelist() or "xl/_rels/workbook.xml.rels" not in workbook.namelist():
                raise ValueError("The spreadsheet could not be read. Save it as CSV if this file stays unreadable.")
            rels = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
            relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
            workbook_xml = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            sheets = []
            for node in workbook_xml.findall("m:sheets/m:sheet", _SHEET_NS):
                target = relmap.get(node.attrib.get(_REL_ID, ""))
                if not target:
                    continue
                path = _zip_target("xl/workbook.xml", target)
                if path not in workbook.namelist():
                    continue
                comments = _sheet_comments(workbook, path)
                cells = _sheet_cells(ElementTree.fromstring(workbook.read(path)), shared)
                sheets.append({"name": node.attrib.get("name") or "Sheet", "cells": cells, "comments": comments})
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The spreadsheet could not be read. Save it as CSV if this file stays unreadable.") from exc
    if not sheets:
        raise ValueError("The spreadsheet has no worksheet.")
    return sheets


def _shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{_SHEET_MAIN}t")) for item in root.findall("m:si", _SHEET_NS)]


def _sheet_cells(sheet, shared: list[str]) -> dict[tuple[int, int], str]:
    cells: dict[tuple[int, int], str] = {}
    for row in sheet.findall("m:sheetData/m:row", _SHEET_NS):
        for cell in row.findall("m:c", _SHEET_NS):
            ref = cell.attrib.get("r", "")
            letters = "".join(character for character in ref if character.isalpha())
            digits = "".join(character for character in ref if character.isdigit())
            if not letters or not digits:
                continue
            text = _cell_text(cell, shared)
            if text:
                cells[(int(digits), _column_index(letters))] = text
    return cells


def _cell_text(cell, shared: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_SHEET_MAIN}t")).strip()
    raw = cell.find("m:v", _SHEET_NS)
    text = "" if raw is None or raw.text is None else raw.text
    if cell.attrib.get("t") == "s" and text.isdigit():
        index = int(text)
        text = shared[index] if index < len(shared) else text
    return text.strip()


def _sheet_comments(workbook: ZipFile, sheet_path: str) -> dict[tuple[int, int], str]:
    folder, name = sheet_path.rsplit("/", 1)
    rel_path = f"{folder}/_rels/{name}.rels"
    if rel_path not in workbook.namelist():
        return {}
    rels = ElementTree.fromstring(workbook.read(rel_path))
    comments: dict[tuple[int, int], str] = {}
    for rel in rels:
        target = rel.attrib.get("Target", "")
        if "comments" not in target:
            continue
        path = _zip_target(sheet_path, target)
        if path not in workbook.namelist():
            continue
        root = ElementTree.fromstring(workbook.read(path))
        for comment in root.findall("m:commentList/m:comment", _SHEET_NS):
            ref = comment.attrib.get("ref", "")
            letters = "".join(character for character in ref if character.isalpha())
            digits = "".join(character for character in ref if character.isdigit())
            if not letters or not digits:
                continue
            text = "".join(node.text or "" for node in comment.iter(f"{_SHEET_MAIN}t")).strip()
            if text:
                comments[(int(digits), _column_index(letters))] = text
    return comments


def _zip_target(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts = base.split("/")[:-1]
    for piece in target.split("/"):
        if piece == "..":
            if parts:
                parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


def _sheet_rows(sheet: dict) -> list[list[str]]:
    cells: dict[tuple[int, int], str] = sheet["cells"]
    if not cells:
        return []
    last_row = max(row for row, _column in cells)
    last_column = max(column for _row, column in cells)
    rows = []
    for row in range(1, last_row + 1):
        rows.append([cells.get((row, column), "") for column in range(last_column + 1)])
    return rows


def _mileage_block_plans(sheet: dict) -> tuple[list[dict], list[str], bool]:
    cells: dict[tuple[int, int], str] = sheet["cells"]
    comments: dict[tuple[int, int], str] = sheet["comments"]
    rows: dict[int, dict[int, str]] = {}
    for (row, column), text in cells.items():
        rows.setdefault(row, {})[column] = text
    header_row = None
    day_columns: dict[int, int] = {}
    notes_column = None
    for row in sorted(rows):
        found = {}
        for column, text in rows[row].items():
            name = _header(text)
            if name in _DAY_INDEX:
                found[column] = _DAY_INDEX[name]
            elif name in {"general_notes", "notes", "coach_notes"}:
                notes_column = column
        if len(found) >= 4:
            header_row = row
            day_columns = found
            break
    if header_row is None:
        return [], [], False
    plans = []
    matched = False
    for row in sorted(number for number in rows if number > header_row):
        label = rows[row].get(0, "").strip()
        if label.lower().startswith("supplemental"):
            break
        week_start = _parse_date(label)
        if week_start is None or week_start.year < 2020:
            continue
        workout_row = next(
            (
                follow
                for follow in range(row + 1, row + 4)
                if rows.get(follow, {}).get(0, "").strip().lower().startswith("workout")
            ),
            None,
        )
        if workout_row is None:
            continue
        matched = True
        monday = week_start - timedelta(days=week_start.weekday())
        week_note = rows[row].get(notes_column, "").strip() if notes_column is not None else ""
        for column, offset in day_columns.items():
            miles = _parse_miles(rows[row].get(column))
            title = rows.get(workout_row, {}).get(column, "").strip()
            if title.lower() in {"rest", "rest day", "off", "off day"}:
                continue
            if (miles is None or miles <= 0) and not title:
                continue
            comment = comments.get((row, column)) or comments.get((workout_row, column)) or ""
            plan_title = title or "Easy"
            plans.append(
                {
                    "scheduled_date": monday + timedelta(days=offset),
                    "title": plan_title[:200],
                    "details": comment.strip()[:4000] or None,
                    "workout_type": _plan_type(plan_title),
                    "distance_meters": None if miles is None or miles <= 0 else miles * METERS_PER_MILE,
                    "warmup": None,
                    "cooldown": None,
                    "repetitions": None,
                    "rep_distance_meters": None,
                    "recovery_seconds": None,
                    "target_pace_seconds_per_mile": None,
                    "intensity": None,
                    "coach_notes": week_note[:1000] or None,
                }
            )
    if not matched:
        return [], [], False
    plans.sort(key=lambda item: (item["scheduled_date"], item["title"]))
    return plans, [], True


def _plan_type(title: str) -> str | None:
    named = normalize_workout_type(title)
    if named:
        return named
    text = title.lower()
    if "race" in text:
        return "race"
    if "long" in text:
        return "long_run"
    if "stride" in text:
        return "strides"
    if text.startswith("lt") or "threshold" in text:
        return "threshold"
    if text in {"easy", "slow"}:
        return "easy"
    return None


def _column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def _rows_to_plans(rows: list[dict], *, week_one: date | None = None) -> tuple[list[dict], list[str]]:
    if not rows:
        return [], ["The file has no workout rows."]
    names = _header_names(rows[0])
    normalized_rows = [_normalize_row(row, names) for row in rows]
    day_columns = {name: _DAY_INDEX[name] for name in names if name in _DAY_INDEX}
    if len(day_columns) >= 4:
        return _week_grid_plans(normalized_rows, day_columns, week_one=week_one)
    plans = []
    errors = []
    for index, normalized in enumerate(normalized_rows, start=2):
        scheduled = _parse_date(normalized.get("date") or normalized.get("scheduled_date"))
        title_key = next((key for key in _TITLE_KEYS if normalized.get(key)), None)
        title = normalized.get(title_key or "")
        if scheduled is None or not title:
            errors.append(f"Row {index} needs a date and a workout title.")
            continue
        distance = _parse_miles(normalized.get("distance") or normalized.get("distance_miles"))
        rep_distance = _parse_miles(normalized.get("rep_distance") or normalized.get("rep_distance_miles"))
        repetitions = _parse_int(normalized.get("repetitions") or normalized.get("reps"))
        recovery = _parse_float(normalized.get("recovery_seconds") or normalized.get("recovery"))
        written = _written_cells(normalized, skip={title_key} if title_key else set())
        plans.append(
            {
                "scheduled_date": scheduled,
                "title": title[:200],
                "details": "\n".join(written) or None,
                "workout_type": normalize_workout_type(normalized.get("workout_type") or normalized.get("type")),
                "distance_meters": None if distance is None else distance * METERS_PER_MILE,
                "warmup": normalized.get("warmup") or None,
                "cooldown": normalized.get("cooldown") or None,
                "repetitions": repetitions,
                "rep_distance_meters": None if rep_distance is None else rep_distance * METERS_PER_MILE,
                "recovery_seconds": recovery,
                "target_pace_seconds_per_mile": parse_pace(normalized.get("target_pace") or normalized.get("pace")),
                "intensity": normalized.get("intensity") or None,
                "coach_notes": normalized.get("notes") or normalized.get("coach_notes") or None,
            }
        )
    return plans, errors


def _header_names(row: dict) -> list[str]:
    names = []
    used: set[str] = set()
    for index, key in enumerate(row.keys()):
        header = _header(str(key) if key else "") or f"column_{index}"
        if header in used:
            header = f"{header}_{index}"
        used.add(header)
        names.append(header)
    return names


def _normalize_row(row: dict, names: list[str]) -> dict[str, str]:
    values = list(row.values())
    return {names[index]: ("" if index >= len(values) or values[index] is None else str(values[index])).strip() for index in range(len(names))}


def _written_cells(normalized: dict[str, str], *, skip: set[str]) -> list[str]:
    hidden = _DATE_KEYS | _DAY_INDEX.keys() | set(_WEEK_KEYS) | skip
    return [f"{key.replace('_', ' ')}: {value}" for key, value in normalized.items() if key not in hidden and value]


def _week_grid_plans(rows: list[dict[str, str]], day_columns: dict[str, int], *, week_one: date | None) -> tuple[list[dict], list[str]]:
    plans = []
    errors = []
    missing_anchor = False
    for index, normalized in enumerate(rows, start=2):
        monday, problem = _grid_monday(normalized, week_one=week_one)
        if monday is None:
            if problem == "week number":
                missing_anchor = True
            else:
                errors.append(f"Row {index} needs a week date or a week number.")
            continue
        for name, offset in day_columns.items():
            text = normalized.get(name) or ""
            if not text or text.lower() in _BLANK_CELLS:
                continue
            first = next((line.strip() for line in text.splitlines() if line.strip()), text)
            title = first[:200]
            plans.append(
                {
                    "scheduled_date": monday + timedelta(days=offset),
                    "title": title,
                    "details": text,
                    "workout_type": "recovery" if title.lower() in {"rest", "rest day", "off", "off day"} else None,
                    "distance_meters": None,
                    "warmup": None,
                    "cooldown": None,
                    "repetitions": None,
                    "rep_distance_meters": None,
                    "recovery_seconds": None,
                    "target_pace_seconds_per_mile": None,
                    "intensity": None,
                    "coach_notes": None,
                }
            )
    if missing_anchor and not plans:
        errors.insert(0, "This spreadsheet uses week numbers. Set the week 1 start date when you upload it.")
    return plans, errors


def _grid_monday(normalized: dict[str, str], *, week_one: date | None) -> tuple[date | None, str | None]:
    for key in _DATE_KEYS:
        parsed = _parse_date(normalized.get(key))
        if parsed is not None:
            return parsed - timedelta(days=parsed.weekday()), None
    for key, value in normalized.items():
        if key in _DAY_INDEX or key in _WEEK_KEYS:
            continue
        parsed = _parse_date(value)
        if parsed is not None:
            return parsed - timedelta(days=parsed.weekday()), None
    for key in _WEEK_KEYS:
        number = _parse_int(normalized.get(key))
        if number is None or number < 1:
            continue
        if week_one is None:
            return None, "week number"
        monday = week_one - timedelta(days=week_one.weekday())
        return monday + timedelta(days=7 * (number - 1)), None
    return None, "undated"


def _header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        serial = int(float(text))
        if 30000 <= serial <= 60000:
            return date(1899, 12, 30) + timedelta(days=serial)
    return None


def _parse_miles(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if match is None:
        return None
    return float(match.group(0))


def _parse_int(value: str | None) -> int | None:
    parsed = _parse_miles(value)
    if parsed is None:
        return None
    return int(parsed)


def _parse_float(value: str | None) -> float | None:
    return _parse_miles(value)


PRESCRIPTION_FIELDS = (
    "scheduled_date",
    "title",
    "workout_type",
    "distance_meters",
    "warmup",
    "cooldown",
    "repetitions",
    "rep_distance_meters",
    "recovery_seconds",
    "target_pace_seconds_per_mile",
    "intensity",
    "coach_notes",
    "details",
)


def prescription_snapshot(plan) -> dict:
    snapshot = {}
    for field in PRESCRIPTION_FIELDS:
        value = getattr(plan, field)
        snapshot[field] = value.isoformat() if isinstance(value, date) else value
    return snapshot


def repetition_measurements(laps: list, evidence: dict | None) -> tuple[int | None, float | None, float | None, float | None]:
    evidence = evidence or {}
    numbers = list(evidence.get("stride_laps") or evidence.get("work_laps") or [])
    selected = [lap for lap in laps if getattr(lap, "lap_number", None) in numbers]
    if not selected:
        return None, None, None, None
    paces = [pace for lap in selected if (pace := pace_seconds_per_mile(lap.average_speed_mps)) is not None]
    distances = [lap.distance_meters for lap in selected if lap.distance_meters is not None]
    recovery_numbers = list(evidence.get("recovery_laps") or [])
    recoveries = [
        lap.duration_seconds
        for lap in laps
        if getattr(lap, "lap_number", None) in recovery_numbers and lap.duration_seconds is not None
    ]
    return (
        len(selected),
        None if not paces else sum(paces) / len(paces),
        None if not distances else sum(distances) / len(distances),
        None if not recoveries else sum(recoveries) / len(recoveries),
    )


def load_plan_view(session, athlete_id: int, *, today: date, last_sync_at: datetime | None) -> dict:
    from sqlalchemy import select

    from app.models import Activity, ActivityLap, PlanRevision, ScheduledWorkout, WorkoutAnalysis, WorkoutClassification

    plans = list(
        session.scalars(
            select(ScheduledWorkout)
            .where(ScheduledWorkout.athlete_id == athlete_id)
            .order_by(ScheduledWorkout.scheduled_date, ScheduledWorkout.id)
        ).all()
    )
    activities = list(session.scalars(select(Activity).where(Activity.athlete_id == athlete_id)).all())
    classifications = {
        row.activity_id: row
        for row in session.scalars(select(WorkoutClassification).where(WorkoutClassification.activity_id.in_([activity.id for activity in activities] or [0]))).all()
    }
    types = {activity_id: row.workout_type for activity_id, row in classifications.items()}
    assigned = assign_matches(plans, activities, types)
    efforts = {}
    analyses = session.scalars(
        select(WorkoutAnalysis)
        .where(WorkoutAnalysis.activity_id.in_([activity.id for activity in activities] or [0]), WorkoutAnalysis.status == "ready")
        .order_by(WorkoutAnalysis.id.desc())
    ).all()
    for row in analyses:
        if row.activity_id not in efforts and isinstance(row.report, dict):
            effort = row.report.get("effort_level")
            efforts[row.activity_id] = effort if isinstance(effort, str) else None
    matched_ids = [activity.id for activity in assigned.values()]
    laps_by_activity: dict[int, list] = {}
    if matched_ids:
        for lap in session.scalars(select(ActivityLap).where(ActivityLap.activity_id.in_(matched_ids))).all():
            laps_by_activity.setdefault(lap.activity_id, []).append(lap)
    revisions = {}
    if plans:
        for revision in session.scalars(
            select(PlanRevision)
            .where(PlanRevision.scheduled_workout_id.in_([plan.id for plan in plans]))
            .order_by(PlanRevision.id.desc())
        ).all():
            revisions.setdefault(revision.scheduled_workout_id, []).append(revision)
    activity_days: dict[date, int] = {}
    for activity in activities:
        day = _local_day(activity)
        if day is not None:
            activity_days[day] = activity_days.get(day, 0) + 1
    later_days = [day for day in activity_days if day is not None]
    statuses = {}
    comparisons = {}
    for plan in plans:
        activity = assigned.get(plan.id)
        comparison = None
        if activity is not None:
            classification = classifications.get(activity.id)
            count, pace, rep_distance, recovery = repetition_measurements(
                laps_by_activity.get(activity.id, []),
                None if classification is None else classification.evidence,
            )
            comparison = compare_execution(
                plan,
                activity,
                actual_type=types.get(activity.id),
                repetition_count=count,
                repetition_pace=pace,
                repetition_distance_meters=rep_distance,
                recovery_seconds=recovery,
                recorded_effort=efforts.get(activity.id),
            )
        covered = sync_covers_date(
            scheduled=plan.scheduled_date,
            later_activity=any(day > plan.scheduled_date for day in later_days),
            last_sync_at=last_sync_at,
        )
        statuses[plan.id] = workout_status(
            plan,
            activity,
            comparison,
            today=today,
            covered=covered,
            same_day_unmatched=activity_days.get(plan.scheduled_date, 0) > 0 and activity is None,
        )
        comparisons[plan.id] = comparison
    weeks = build_weeks(plans, activities, assigned, statuses, today=today)
    workouts = [_workout_payload(plan, assigned.get(plan.id), statuses[plan.id], comparisons[plan.id], activities, revisions.get(plan.id, [])) for plan in plans]
    current = next((week for week in weeks if week["in_progress"]), None)
    return {
        "trend": adherence_trend(weeks),
        "weeks": weeks,
        "workouts": workouts,
        "current_week": current,
        "adherence_notes": current_week_flags(weeks, workouts, today=today),
        "key_workout_status": key_workout_status(workouts, current),
    }


def _workout_payload(plan, activity, status: str, comparison: dict | None, activities: list, revisions: list) -> dict:
    same_day = [item for item in activities if _local_day(item) == plan.scheduled_date]
    return {
        "id": plan.id,
        "scheduled_date": plan.scheduled_date.isoformat(),
        "title": plan.title,
        "workout_type": plan.workout_type,
        "distance_miles": miles_from_meters(plan.distance_meters),
        "warmup": plan.warmup,
        "cooldown": plan.cooldown,
        "repetitions": plan.repetitions,
        "rep_distance_miles": miles_from_meters(plan.rep_distance_meters),
        "recovery_seconds": plan.recovery_seconds,
        "target_pace": format_pace(plan.target_pace_seconds_per_mile),
        "intensity": plan.intensity,
        "coach_notes": plan.coach_notes,
        "details": plan.details,
        "status": status,
        "execution": None if comparison is None else comparison["execution"],
        "summary": None if comparison is None else comparison["summary"],
        "comparison": comparison,
        "match": None
        if activity is None
        else {
            "garmin_activity_id": activity.garmin_activity_id,
            "name": activity.name,
            "source": plan.match_source or "auto",
            "distance_miles": miles_from_meters(activity.distance_meters),
        },
        "candidates": [
            {
                "garmin_activity_id": item.garmin_activity_id,
                "name": item.name,
                "distance_miles": miles_from_meters(item.distance_meters),
            }
            for item in same_day
        ],
        "original_prescription": plan.original_prescription,
        "revisions": [
            {"created_at": revision.created_at.isoformat(), "prescription": revision.prescription}
            for revision in revisions[:8]
        ],
    }
