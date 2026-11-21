"""Sum imported distance over a recent window.

SQLite returns datetimes without a timezone. Comparisons use UTC for both sides.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class DatedDistance(Protocol):
    start_time_utc: datetime | None
    distance_meters: float | None


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def window_stats(
    activities: list[DatedDistance],
    *,
    now: datetime,
    days: int,
) -> tuple[int, int, float | None]:
    cutoff = as_utc(now) - timedelta(days=days)
    selected = [
        activity
        for activity in activities
        if activity.start_time_utc is not None and as_utc(activity.start_time_utc) >= cutoff
    ]
    distances = [activity.distance_meters for activity in selected if activity.distance_meters is not None]
    total = sum(distances) if distances else None
    return len(selected), len(distances), total
