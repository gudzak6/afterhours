import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Activity, Athlete, ScheduledWorkout, WorkoutAnalysis
from app.services.coach_review import AWAITING_ACTIVITY, AWAITING_ANALYSIS, review_for_athlete


def _paragraph() -> str:
    words = "The stored analysis describes controlled running against the planned session.".split()
    text: list[str] = []
    while len(text) < 100:
        text.extend(words)
    return " ".join(text[:100])


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _athlete(session: Session) -> Athlete:
    now = datetime(2026, 11, 23, tzinfo=UTC)
    athlete = Athlete(display_name="Joey", created_at=now, updated_at=now)
    session.add(athlete)
    session.commit()
    return athlete


def _activity(session: Session, athlete: Athlete, garmin_id: int, meters: float, day: str = "2026-11-23T08:00:00") -> Activity:
    now = datetime(2026, 11, 23, tzinfo=UTC)
    activity = Activity(
        athlete_id=athlete.id,
        garmin_activity_id=garmin_id,
        name="Run",
        start_time_local=day,
        distance_meters=meters,
        duration_seconds=2400,
        average_speed_mps=meters / 2400,
        present_fields=[],
        raw_summary={},
        created_at=now,
        updated_at=now,
    )
    session.add(activity)
    session.commit()
    return activity


def _analysis(session: Session, activity: Activity, finding: str) -> None:
    session.add(
        WorkoutAnalysis(
            activity_id=activity.id,
            status="ready",
            model="test",
            report={"workout_analysis": finding, "training_impact": "Aerobic work.", "coach_takeaway": "Leave the next day as planned."},
            created_at=datetime(2026, 11, 23, tzinfo=UTC),
        )
    )
    session.commit()


def test_review_waits_until_an_activity_is_recorded():
    session = _session()
    athlete = _athlete(session)

    def complete(_settings, _messages):
        raise AssertionError("The model should not run without an activity.")

    result = review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=complete)
    assert result["paragraph"] == AWAITING_ACTIVITY
    assert result["status"] == "waiting"


def test_review_waits_for_the_stored_analysis():
    session = _session()
    athlete = _athlete(session)
    _activity(session, athlete, 1, 6437)

    result = review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=lambda *_args: pytest.fail("no analysis"))
    assert result["paragraph"] == AWAITING_ANALYSIS


def test_review_uses_the_stored_analysis_and_then_the_cache():
    session = _session()
    athlete = _athlete(session)
    now = datetime(2026, 11, 23, tzinfo=UTC)
    activity = _activity(session, athlete, 11, 6437)
    _activity(session, athlete, 12, 1609)
    _analysis(session, activity, "Four miles stayed controlled.")
    session.add_all(
        [
            ScheduledWorkout(athlete_id=athlete.id, scheduled_date=date(2026, 11, 23), title="Easy", distance_meters=6437, workout_type="easy", created_at=now),
            ScheduledWorkout(athlete_id=athlete.id, scheduled_date=date(2026, 11, 24), title="Hills", workout_type="hill_sprints", created_at=now),
        ]
    )
    session.commit()
    calls: list[dict] = []

    def complete(_settings, messages):
        calls.append(json.loads(messages[-1]["content"] if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("{") else messages[1]["content"]))
        return json.dumps({"paragraph": _paragraph()})

    first = review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=complete)
    second = review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=complete)
    assert first["paragraph"] == _paragraph()
    assert second["cached"] is True
    assert len(calls) == 1
    packet = calls[0]
    assert packet["tomorrow"][0]["title"] == "Hills"
    assert packet["matched_sessions"][0]["activity"]["distance_miles"] == 4.0
    assert packet["matched_sessions"][0]["stored_analysis"]["workout_analysis"] == "Four miles stayed controlled."
    assert len(packet["unmatched_activities"]) == 1
    assert "athlete_name" not in packet

    _analysis(session, activity, "The same run was read again.")
    review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=complete)
    assert len(calls) == 2


def test_review_rejects_a_bulleted_paragraph_and_retries():
    session = _session()
    athlete = _athlete(session)
    activity = _activity(session, athlete, 21, 5000)
    _analysis(session, activity, "A recorded run.")
    calls = {"count": 0}

    def complete(_settings, _messages):
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps({"paragraph": "- Too short."})
        return json.dumps({"paragraph": _paragraph()})

    result = review_for_athlete(session, None, athlete, date(2026, 11, 23), complete=complete)
    assert calls["count"] == 2
    assert result["paragraph"] == _paragraph()
