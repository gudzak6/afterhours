"""Running averages and best efforts from stored activities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.garmin.mapping import METERS_PER_MILE
from app.models import ActivitySample, TrainingGoal
from app.services.history import FEET_PER_METER

# A window faster than this is treated as a bad distance sample, not a best effort.
MAX_SPEED_MPS = 11.0

EFFORTS = (
    ("400m", 400.0),
    ("1/2 mile", 804.672),
    ("1K", 1000.0),
    ("1 mile", 1609.344),
    ("2 mile", 3218.688),
    ("5K", 5000.0),
    ("10K", 10000.0),
    ("15K", 15000.0),
    ("10 mile", 16093.44),
    ("20K", 20000.0),
    ("Half-Marathon", 21097.5),
    ("30K", 30000.0),
    ("Marathon", 42195.0),
    ("50K", 50000.0),
)


def _is_run(activity) -> bool:
    key = (activity.activity_type_key or "").lower()
    return "run" in key


def _local_date(activity) -> date | None:
    local = activity.start_time_local
    if isinstance(local, str) and len(local) >= 10:
        try:
            return date.fromisoformat(local[:10])
        except ValueError:
            return None
    return None


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _last_four_weeks(runs: list, *, today: date) -> dict:
    current = _week_start(today)
    window = [current - timedelta(days=7 * (4 - index)) for index in range(4)]
    selected = []
    for activity in runs:
        day = _local_date(activity)
        if day is None:
            continue
        if _week_start(day) in window:
            selected.append(activity)
    if not selected:
        return {
            "activities_per_week": None,
            "distance_miles": None,
            "duration_seconds": None,
            "elevation_feet": None,
        }
    count = len(selected)
    miles = [activity.distance_meters for activity in selected if activity.distance_meters is not None]
    durations = [activity.duration_seconds for activity in selected if activity.duration_seconds is not None]
    climbs = [activity.elevation_gain_meters for activity in selected if activity.elevation_gain_meters is not None]
    return {
        "activities_per_week": count / 4,
        "distance_miles": None if not miles else sum(miles) / METERS_PER_MILE / 4,
        "duration_seconds": None if not durations else sum(durations) / 4,
        "elevation_feet": None if not climbs else sum(climbs) * FEET_PER_METER / 4,
    }


def _segments(points: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    last_distance = None
    for elapsed, distance in points:
        if last_distance is not None and distance + 1 < last_distance:
            if len(current) >= 2:
                segments.append(current)
            current = []
        current.append((elapsed, distance))
        last_distance = distance
    if len(current) >= 2:
        segments.append(current)
    return segments


def _fastest(points: list[tuple[float, float]], target: float) -> float | None:
    best = None
    index = 0
    for end in range(len(points)):
        elapsed, distance = points[end]
        while index + 1 <= end and distance - points[index + 1][1] >= target:
            index += 1
        if distance - points[index][1] < target:
            continue
        start_distance = distance - target
        if start_distance < points[index][1]:
            continue
        next_index = index + 1 if index + 1 <= end else end
        start_elapsed, start_span = points[index]
        next_elapsed, next_span = points[next_index]
        if next_span <= start_span:
            start_time = start_elapsed
        else:
            fraction = min(1.0, (start_distance - start_span) / (next_span - start_span))
            start_time = start_elapsed + fraction * (next_elapsed - start_elapsed)
        duration = elapsed - start_time
        if duration <= 0 or target / duration > MAX_SPEED_MPS:
            continue
        if best is None or duration < best:
            best = duration
    return best


def _best_efforts(session: Session, runs: list) -> list[dict]:
    by_id = {activity.id: activity for activity in runs if (activity.distance_meters or 0) >= EFFORTS[0][1]}
    best: dict[str, tuple[float, object]] = {}
    if not by_id:
        return [{"label": label, "duration_seconds": None, "garmin_activity_id": None, "start_time_local": None} for label, _distance in EFFORTS]
    rows = session.execute(
        select(ActivitySample.activity_id, ActivitySample.elapsed_seconds, ActivitySample.distance_meters)
        .where(
            ActivitySample.activity_id.in_(by_id),
            ActivitySample.elapsed_seconds.is_not(None),
            ActivitySample.distance_meters.is_not(None),
        )
        .order_by(ActivitySample.activity_id, ActivitySample.elapsed_seconds)
    ).all()
    grouped: dict[int, list[tuple[float, float]]] = {}
    for activity_id, elapsed, distance in rows:
        grouped.setdefault(activity_id, []).append((float(elapsed), float(distance)))
    for activity_id, points in grouped.items():
        activity = by_id[activity_id]
        total = activity.distance_meters or 0
        for segment in _segments(points):
            for label, target in EFFORTS:
                if total + 5 < target:
                    continue
                duration = _fastest(segment, target)
                if duration is None:
                    continue
                current = best.get(label)
                if current is None or duration < current[0]:
                    best[label] = (duration, activity)
    efforts = []
    for label, _target in EFFORTS:
        found = best.get(label)
        if found is None:
            efforts.append({"label": label, "duration_seconds": None, "garmin_activity_id": None, "start_time_local": None})
            continue
        duration, activity = found
        efforts.append(
            {
                "label": label,
                "duration_seconds": duration,
                "garmin_activity_id": activity.garmin_activity_id,
                "start_time_local": activity.start_time_local,
            }
        )
    return efforts


def apply_saved_efforts(session: Session, athlete_id: int, efforts: list[dict]) -> list[dict]:
    goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete_id))
    saved = goal.personal_records.get("best_efforts") if goal is not None and isinstance(goal.personal_records, dict) else None
    if not isinstance(saved, dict):
        return efforts
    for effort in efforts:
        value = saved.get(effort["label"])
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        effort["duration_seconds"] = float(value)
        effort["garmin_activity_id"] = None
        effort["start_time_local"] = None
        effort["manual"] = True
    return efforts


def save_best_effort(session: Session, athlete_id: int, label: str, duration_seconds: float | None) -> None:
    known = {name for name, _distance in EFFORTS}
    if label not in known:
        raise ValueError("That distance is not a best effort.")
    goal = session.scalar(select(TrainingGoal).where(TrainingGoal.athlete_id == athlete_id))
    if goal is None:
        goal = TrainingGoal(athlete_id=athlete_id, personal_records={}, updated_at=datetime.now(UTC))
        session.add(goal)
    records = dict(goal.personal_records or {})
    efforts = dict(records.get("best_efforts") or {})
    if duration_seconds is None or duration_seconds <= 0:
        efforts.pop(label, None)
    else:
        efforts[label] = float(duration_seconds)
    records["best_efforts"] = efforts
    goal.personal_records = records
    goal.updated_at = datetime.now(UTC)
    session.commit()


def running_stats(session: Session, activities: list, *, today: date, athlete_id: int | None = None) -> dict:
    runs = [activity for activity in activities if _is_run(activity)]
    efforts = _best_efforts(session, runs)
    if athlete_id is not None:
        apply_saved_efforts(session, athlete_id, efforts)
    return {"last_4_weeks": _last_four_weeks(runs, today=today), "best_efforts": efforts}
