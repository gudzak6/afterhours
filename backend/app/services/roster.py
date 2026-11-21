"""Roster status from stored activities, plans, and analyses. Missing data stays unlabeled."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.mileage import as_utc


def attention_reasons(
    *,
    last_activity_at: datetime | None,
    now: datetime,
    missed_planned_sessions: int,
    latest_effort: str | None,
    latest_goal_status: str | None,
) -> list[str]:
    reasons: list[str] = []
    if missed_planned_sessions > 0:
        reasons.append(
            f"{missed_planned_sessions} planned session{'s' if missed_planned_sessions != 1 else ''} confirmed missed"
        )
    if last_activity_at is not None and as_utc(last_activity_at) < as_utc(now) - timedelta(days=3):
        reasons.append("No activity in the last 3 days")
    if latest_effort == "Hard Effort" and last_activity_at is not None and as_utc(last_activity_at) >= as_utc(now) - timedelta(days=2):
        reasons.append("Latest analysis rated the effort hard")
    if latest_goal_status == "needs_attention":
        reasons.append("Latest analysis marked goal progress as needing attention")
    return reasons


def training_status(reasons: list[str], *, has_activities: bool, goal_status: str | None) -> str:
    if reasons:
        return "attention"
    if not has_activities:
        return "no_data"
    if goal_status == "on_track":
        return "on_track"
    if goal_status == "building":
        return "building"
    return "steady"
