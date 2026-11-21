"""Training-history counts from stored activities and classifications."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.garmin.mapping import METERS_PER_MILE
from app.services.mileage import as_utc

FEET_PER_METER = 3.280839895

HARD_WORKOUT_TYPES = {"strides", "intervals", "tempo", "threshold"}


def _local_day(activity) -> str | None:
    local = activity.start_time_local
    if isinstance(local, str) and len(local) >= 10:
        return local[:10]
    if activity.start_time_utc is None:
        return None
    return as_utc(activity.start_time_utc).date().isoformat()


def _local_date(activity) -> date | None:
    local = activity.start_time_local
    if isinstance(local, str) and len(local) >= 10:
        try:
            return date.fromisoformat(local[:10])
        except ValueError:
            return None
    return None


def _miles(activities: list) -> float | None:
    distances = [activity.distance_meters for activity in activities if activity.distance_meters is not None]
    if not distances:
        return None
    return sum(distances) / METERS_PER_MILE


def _duration(activities: list) -> float | None:
    values = [activity.duration_seconds for activity in activities if activity.duration_seconds is not None]
    if not values:
        return None
    return sum(values)


def _feet(activities: list) -> float | None:
    values = [activity.elevation_gain_meters for activity in activities if activity.elevation_gain_meters is not None]
    if not values:
        return None
    return sum(values) * FEET_PER_METER


def mileage_chart(activities: list, *, today: date) -> dict:
    """Weekly totals from the first stored run through the current Monday–Sunday week."""
    dated = [(day, activity) for activity in activities if (day := _local_date(activity)) is not None]
    current_start = today - timedelta(days=today.weekday())
    current_end = current_start + timedelta(days=6)
    if dated:
        first = min(day for day, _activity in dated)
        start = first - timedelta(days=first.weekday())
    else:
        start = current_start
    if start > current_start:
        start = current_start
    weeks = []
    cursor = start
    current_activities: list = []
    while cursor <= current_start:
        week_end = cursor + timedelta(days=6)
        selected = [activity for day, activity in dated if cursor <= day <= week_end]
        if cursor == current_start:
            current_activities = selected
        weeks.append(
            {
                "week_start": cursor.isoformat(),
                "week_end": week_end.isoformat(),
                "distance_miles": _miles(selected),
                "activity_count": len(selected),
                "current": cursor == current_start,
            }
        )
        cursor += timedelta(days=7)
    runs = sorted(current_activities, key=lambda activity: activity.start_time_local or "")
    return {
        "week_start": current_start.isoformat(),
        "week_end": current_end.isoformat(),
        "distance_miles": _miles(current_activities),
        "duration_seconds": _duration(current_activities),
        "elevation_feet": _feet(current_activities),
        "weeks": weeks,
        "runs": [
            {
                "garmin_activity_id": activity.garmin_activity_id,
                "name": activity.name,
                "start_time_local": activity.start_time_local,
                "distance_miles": None if activity.distance_meters is None else activity.distance_meters / METERS_PER_MILE,
                "duration_seconds": activity.duration_seconds,
                "elevation_feet": None if activity.elevation_gain_meters is None else activity.elevation_gain_meters * FEET_PER_METER,
            }
            for activity in runs
        ],
    }


def weekly_mileage(activities: list, *, now: datetime, weeks: int = 8) -> list[dict]:
    end = as_utc(now)
    start = (end - timedelta(days=end.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start - timedelta(weeks=weeks - 1)
    buckets = []
    for index in range(weeks):
        week_start = start + timedelta(weeks=index)
        week_end = week_start + timedelta(weeks=1)
        selected = [
            activity
            for activity in activities
            if activity.start_time_utc is not None
            and week_start <= as_utc(activity.start_time_utc) < week_end
        ]
        distances = [activity.distance_meters for activity in selected if activity.distance_meters is not None]
        buckets.append(
            {
                "week_start": week_start.date().isoformat(),
                "activity_count": len(selected),
                "distance_meters": sum(distances) if distances else None,
                "distance_miles": None if not distances else sum(distances) / METERS_PER_MILE,
            }
        )
    return buckets


def training_history(activities: list, classifications: dict[int, str], *, now: datetime) -> dict:
    cutoff = as_utc(now) - timedelta(days=28)
    recent = [
        activity
        for activity in activities
        if activity.start_time_utc is not None and as_utc(activity.start_time_utc) >= cutoff
    ]
    counts: dict[str, int] = {}
    hard = 0
    for activity in recent:
        workout_type = classifications.get(activity.id)
        if not workout_type:
            continue
        counts[workout_type] = counts.get(workout_type, 0) + 1
        if workout_type in HARD_WORKOUT_TYPES:
            hard += 1
    active_days = {day for activity in recent if (day := _local_day(activity))}
    return {
        "workout_counts": counts,
        "hard_workouts_28_days": hard,
        "active_days_28": len(active_days),
        "weekly_mileage": weekly_mileage(activities, now=now),
    }
