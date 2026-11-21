"""Deterministic coaching facts for one athlete on one selected day.

Numbers come from stored activities, laps, and planned workouts. A missing
measurement stays null. It is never filled in with zero.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.garmin.mapping import METERS_PER_MILE, pace_seconds_per_mile
from app.services.adherence import (
    _local_day,
    assign_matches,
    compare_execution,
    repetition_measurements,
    sync_covers_date,
    workout_status,
)

WINDOWS = (7, 14, 28, 90)


def build_facts_packet(
    *,
    athlete_id: int,
    athlete_name: str,
    selected_date: date,
    activities: list,
    plans: list,
    laps_by_activity: dict[int, list] | None = None,
    lap_evidence: dict[int, dict] | None = None,
    activity_types: dict[int, str | None] | None = None,
    last_sync_at: datetime | None = None,
    garmin_status: str | None = None,
    calculated_at: datetime | None = None,
) -> dict:
    """Return the facts the coaching analyst is allowed to interpret."""
    laps_by_activity = laps_by_activity or {}
    lap_evidence = lap_evidence or {}
    activity_types = activity_types or {}
    dated = [activity for activity in activities if _local_day(activity) is not None]
    undated = [activity for activity in activities if _local_day(activity) is None]
    assigned = assign_matches(plans, dated, activity_types)
    later_days = [day for activity in dated if (day := _local_day(activity)) is not None]
    day_counts: dict[date, int] = {}
    for activity in dated:
        day = _local_day(activity)
        if day is not None:
            day_counts[day] = day_counts.get(day, 0) + 1

    judged: dict[int, tuple[str, dict | None, bool]] = {}
    for plan in plans:
        activity = assigned.get(plan.id)
        laps = [] if activity is None else laps_by_activity.get(activity.id, [])
        evidence = None if activity is None else lap_evidence.get(activity.id)
        count, pace, rep_distance, recovery = repetition_measurements(laps, evidence)
        comparison = None
        if activity is not None:
            comparison = compare_execution(
                plan,
                activity,
                actual_type=activity_types.get(activity.id),
                repetition_count=count,
                repetition_pace=pace,
                repetition_distance_meters=rep_distance,
                recovery_seconds=recovery,
                recorded_effort=None,
            )
        covered = sync_covers_date(
            scheduled=plan.scheduled_date,
            later_activity=any(day > plan.scheduled_date for day in later_days),
            last_sync_at=last_sync_at,
        )
        status = workout_status(
            plan,
            activity,
            comparison,
            today=selected_date,
            covered=covered,
            same_day_unmatched=day_counts.get(plan.scheduled_date, 0) > 0 and activity is None,
        )
        judged[plan.id] = (status, comparison, bool(laps))

    windows = {
        str(days): _window(
            days=days,
            selected_date=selected_date,
            activities=dated,
            plans=plans,
            judged=judged,
            assigned=assigned,
            laps_by_activity=laps_by_activity,
        )
        for days in WINDOWS
    }
    return {
        "athlete_id": athlete_id,
        "athlete_name": athlete_name,
        "selected_date": selected_date.isoformat(),
        "calculated_at": None if calculated_at is None else calculated_at.isoformat(),
        "data_availability": _availability(
            activities=activities,
            dated=dated,
            undated=undated,
            plans=plans,
            laps_by_activity=laps_by_activity,
            last_sync_at=last_sync_at,
            garmin_status=garmin_status,
        ),
        "selected_day": _selected_day(selected_date, dated, plans, judged, assigned),
        "windows": windows,
        "training_load": _training_load(dated, selected_date),
        "upcoming": _upcoming(plans, selected_date),
    }


def _availability(*, activities, dated, undated, plans, laps_by_activity, last_sync_at, garmin_status) -> dict:
    latest = _latest_activity(dated)
    return {
        "stored_activities": len(activities),
        "dated_activities": len(dated),
        "undated_activities": len(undated),
        "activities_with_distance": sum(1 for activity in dated if activity.distance_meters is not None),
        "activities_with_pace": sum(1 for activity in dated if _pace(activity) is not None),
        "activities_with_heart_rate": sum(1 for activity in dated if _heart_rate(activity) is not None),
        "activities_with_laps": sum(1 for activity in dated if laps_by_activity.get(activity.id)),
        "planned_workouts": len(plans),
        "last_activity_local": None if latest is None else latest.start_time_local,
        "last_activity_stored_at": _stored_at(latest),
        "last_sync_at": None if last_sync_at is None else last_sync_at.isoformat(),
        "garmin_status": garmin_status,
    }


def _selected_day(selected_date, activities, plans, judged, assigned) -> dict:
    day_plans = [plan for plan in plans if plan.scheduled_date == selected_date]
    day_activities = [activity for activity in activities if _local_day(activity) == selected_date]
    return {
        "planned_workouts": [_plan_fact(plan, judged, assigned) for plan in day_plans],
        "activities": [_activity_fact(activity) for activity in day_activities],
    }


def _window(*, days, selected_date, activities, plans, judged, assigned, laps_by_activity) -> dict:
    start = selected_date - timedelta(days=days - 1)
    previous_start = start - timedelta(days=days)
    current = [activity for activity in activities if _in_range(activity, start, selected_date)]
    previous = [activity for activity in activities if _in_range(activity, previous_start, start - timedelta(days=1))]
    due = [plan for plan in plans if start <= plan.scheduled_date <= selected_date]
    counts = _status_counts(due, judged)
    planned_due = len(due)
    return {
        "start": start.isoformat(),
        "end": selected_date.isoformat(),
        "activity_count": len(current),
        "activities_with_distance": sum(1 for activity in current if activity.distance_meters is not None),
        "activities_with_pace": sum(1 for activity in current if _pace(activity) is not None),
        "activities_with_heart_rate": sum(1 for activity in current if _heart_rate(activity) is not None),
        "activities_with_laps": sum(1 for activity in current if laps_by_activity.get(activity.id)),
        "distance_miles": _miles(current),
        "pace": _trend(current, previous, _pace),
        "heart_rate": _trend(current, previous, _heart_rate),
        "adherence": {
            "planned_workouts": planned_due,
            "completed": counts["completed"],
            "partially_completed": counts["partially_completed"],
            "confirmed_missed": counts["confirmed_missed"],
            "unmatched": counts["unmatched"],
            "scheduled": counts["scheduled"],
            "completed_ratio": None if planned_due == 0 else round(counts["completed"] / planned_due, 3),
        },
        "interval_execution": [
            _interval_fact(plan, judged, assigned, laps_by_activity)
            for plan in due
            if plan.repetitions is not None
        ],
    }


def _training_load(activities, selected_date: date) -> dict:
    acute = _miles(_between(activities, selected_date - timedelta(days=6), selected_date))
    blocks = []
    for index in range(1, 5):
        end = selected_date - timedelta(days=7 * index)
        start = end - timedelta(days=6)
        blocks.append(_miles(_between(activities, start, end)))
    known = [miles for miles in blocks if miles is not None]
    chronic = None if not known else round(sum(known) / len(known), 2)
    ratio = None
    if acute is not None and chronic:
        ratio = round(acute / chronic, 2)
    return {
        "acute_miles": acute,
        "acute_days": 7,
        "chronic_miles": chronic,
        "chronic_blocks_with_distance": len(known),
        "chronic_blocks": 4,
        "acute_chronic_ratio": ratio,
    }


def _upcoming(plans, selected_date: date) -> list[dict]:
    horizon = selected_date + timedelta(days=14)
    chosen = [plan for plan in plans if selected_date < plan.scheduled_date <= horizon]
    chosen.sort(key=lambda plan: (plan.scheduled_date, plan.id))
    return [
        {
            "id": plan.id,
            "scheduled_date": plan.scheduled_date.isoformat(),
            "title": plan.title,
            "workout_type": plan.workout_type,
            "distance_miles": _round_miles(plan.distance_meters),
            "repetitions": plan.repetitions,
            "target_pace_seconds_per_mile": plan.target_pace_seconds_per_mile,
        }
        for plan in chosen
    ]


def _plan_fact(plan, judged, assigned) -> dict:
    status, comparison, has_laps = judged[plan.id]
    activity = assigned.get(plan.id)
    return {
        "id": plan.id,
        "title": plan.title,
        "workout_type": plan.workout_type,
        "status": status,
        "garmin_activity_id": None if activity is None else activity.garmin_activity_id,
        "laps_stored": has_laps,
        "comparison": _comparison_numbers(comparison),
    }


def _interval_fact(plan, judged, assigned, laps_by_activity) -> dict:
    status, comparison, has_laps = judged[plan.id]
    activity = assigned.get(plan.id)
    laps_stored = False if activity is None else bool(laps_by_activity.get(activity.id))
    actual = None if comparison is None else comparison.get("actual_repetitions")
    missing = None
    if plan.repetitions is not None and actual is None:
        missing = "no_matched_activity" if activity is None else "work_laps_not_identified" if not laps_stored else "work_laps_not_labeled"
    return {
        "scheduled_date": plan.scheduled_date.isoformat(),
        "title": plan.title,
        "status": status,
        "planned_repetitions": plan.repetitions,
        "actual_repetitions": actual,
        "actual_repetitions_missing": missing,
        "planned_pace_seconds_per_mile": None if comparison is None else comparison.get("planned_pace_seconds_per_mile"),
        "actual_pace_seconds_per_mile": None if comparison is None else _round(comparison.get("actual_pace_seconds_per_mile"), 1),
        "execution": None if comparison is None else comparison.get("execution"),
        "laps_stored": laps_stored or has_laps,
    }


def _comparison_numbers(comparison: dict | None) -> dict | None:
    if comparison is None:
        return None
    return {
        "planned_distance_miles": _round(comparison.get("planned_distance_miles"), 2),
        "actual_distance_miles": _round(comparison.get("actual_distance_miles"), 2),
        "planned_pace_seconds_per_mile": comparison.get("planned_pace_seconds_per_mile"),
        "actual_pace_seconds_per_mile": _round(comparison.get("actual_pace_seconds_per_mile"), 1),
        "planned_repetitions": comparison.get("planned_repetitions"),
        "actual_repetitions": comparison.get("actual_repetitions"),
        "execution": comparison.get("execution"),
    }


def _activity_fact(activity) -> dict:
    present = []
    miles = None if activity.distance_meters is None else round(activity.distance_meters / METERS_PER_MILE, 2)
    pace = _pace(activity)
    heart = _heart_rate(activity)
    if miles is not None:
        present.append("distance")
    if pace is not None:
        present.append("pace")
    if heart is not None:
        present.append("heart_rate")
    return {
        "garmin_activity_id": activity.garmin_activity_id,
        "name": activity.name,
        "start_time_local": activity.start_time_local,
        "stored_at": _stored_at(activity),
        "distance_miles": miles,
        "pace_seconds_per_mile": _round(pace, 1),
        "average_heart_rate_bpm": _round(heart, 1),
        "fields_present": present,
    }


def _trend(current, previous, reader) -> dict:
    current_values = [value for activity in current if (value := reader(activity)) is not None]
    previous_values = [value for activity in previous if (value := reader(activity)) is not None]
    current_average = None if not current_values else sum(current_values) / len(current_values)
    previous_average = None if not previous_values else sum(previous_values) / len(previous_values)
    change = None
    if current_average is not None and previous_average is not None:
        change = current_average - previous_average
    return {
        "average": _round(current_average, 1),
        "samples": len(current_values),
        "previous_average": _round(previous_average, 1),
        "previous_samples": len(previous_values),
        "change_from_previous": _round(change, 1),
    }


def _status_counts(plans, judged) -> dict[str, int]:
    counts = {key: 0 for key in ("completed", "partially_completed", "confirmed_missed", "unmatched", "scheduled")}
    for plan in plans:
        status = judged[plan.id][0]
        if status in counts:
            counts[status] += 1
    return counts


def _miles(activities) -> float | None:
    distances = [activity.distance_meters for activity in activities if activity.distance_meters is not None]
    if not distances:
        return None
    return round(sum(distances) / METERS_PER_MILE, 2)


def _between(activities, start: date, end: date) -> list:
    return [activity for activity in activities if _in_range(activity, start, end)]


def _in_range(activity, start: date, end: date) -> bool:
    day = _local_day(activity)
    return day is not None and start <= day <= end


def _pace(activity) -> float | None:
    pace = pace_seconds_per_mile(getattr(activity, "average_speed_mps", None))
    if pace is not None:
        return pace
    distance = getattr(activity, "distance_meters", None)
    duration = getattr(activity, "duration_seconds", None)
    if isinstance(distance, (int, float)) and isinstance(duration, (int, float)) and distance > 0 and duration > 0:
        return duration / (distance / METERS_PER_MILE)
    return None


def _heart_rate(activity) -> float | None:
    value = getattr(activity, "average_heart_rate_bpm", None)
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _round_miles(meters) -> float | None:
    if meters is None:
        return None
    return round(meters / METERS_PER_MILE, 2)


def _round(value, places: int):
    if value is None:
        return None
    return round(value, places)


def _latest_activity(activities):
    dated = [activity for activity in activities if activity.start_time_local]
    if not dated:
        return None
    return max(dated, key=lambda activity: activity.start_time_local)


def _stored_at(activity) -> str | None:
    if activity is None:
        return None
    stored = getattr(activity, "updated_at", None)
    if stored is None:
        return None
    return stored.isoformat()
