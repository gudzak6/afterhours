from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Coach, CoachingBrief
from app.services.brief import brief_for_day, prepare_brief_payload


def test_friday_does_not_show_an_older_brief():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    coach = Coach(
        display_name="Coach Owen",
        timezone="America/New_York",
        email_notifications_enabled=False,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    session.add(coach)
    session.flush()
    session.add(
        CoachingBrief(
            coach_id=coach.id,
            brief_date=date(2026, 11, 11),
            status="ready",
            model="test",
            report={"daily_summary": "Athlete logged a run today. Test athlete has no training data."},
            created_at=datetime(2026, 11, 12, 2, 4, tzinfo=UTC),
        )
    )
    session.commit()

    assert brief_for_day(session, coach, date(2026, 11, 20)) is None
    stored = brief_for_day(session, coach, date(2026, 11, 11))
    assert stored is not None
    assert stored.report["daily_summary"].startswith("Athlete logged a run")


def test_upcoming_brief_uses_the_plan_and_prior_training():
    payload = prepare_brief_payload(
        date(2026, 11, 23),
        date(2026, 11, 21),
        [
            {
                "athlete_id": 4,
                "athlete_name": "Joey",
                "attention_reasons": ["4 confirmed missed sessions"],
                "race_goal": "New York City Marathon",
                "recent_activity": "New York Running · 8.12 mi",
                "stored_summary": "Controlled aerobic execution.",
                "weekly_miles": None,
            }
        ],
        {4: [{"title": "Drills/hill strides", "detail": "5.00 mi", "prescription": "Hill strides x 4"}]},
        {4: [{"scheduled_date": "2026-11-25", "title": "LT1/2", "detail": "8.00 mi"}]},
    )
    assert payload["day_relation"] == "upcoming"
    athlete = payload["roster"][0]
    assert athlete["planned_for_brief_date"][0]["prescription"] == "Hill strides x 4"
    assert athlete["surrounding_workouts"][0]["title"] == "LT1/2"
    assert athlete["prior_training"]["race_goal"] == "New York City Marathon"
    assert athlete["prior_training"]["stored_summary"] == "Controlled aerobic execution."
    assert "attention_reasons" not in athlete
    assert "weekly_miles" not in athlete["prior_training"]


def test_completed_day_keeps_history_before_the_brief_date():
    payload = prepare_brief_payload(
        date(2026, 11, 20),
        date(2026, 11, 21),
        [
            {
                "athlete_id": 4,
                "athlete_name": "Joey",
                "recent_runs": [
                    {"date": "2026-11-21", "distance_miles": 6.0, "pace_seconds_per_mile": 500},
                    {"date": "2026-11-20", "distance_miles": 8.12, "pace_seconds_per_mile": 480, "average_heart_rate_bpm": 129},
                    {"date": "2026-11-18", "distance_miles": 8.55, "pace_seconds_per_mile": 490, "average_heart_rate_bpm": 126},
                ],
                "stored_analyses": [
                    {"activity_date": "2026-11-21", "summary": "A later day."},
                    {"activity_date": "2026-11-20", "summary": "Heart rate rose 2 bpm."},
                ],
                "data_not_stored": ["resting_heart_rate", "hrv"],
            }
        ],
        {4: [{"title": "Easy", "detail": "5.00 mi"}]},
        {4: [{"scheduled_date": "2026-11-23", "title": "Drills/hill strides"}]},
    )
    assert payload["day_relation"] == "past"
    athlete = payload["roster"][0]
    assert [run["date"] for run in athlete["runs_on_brief_date"]] == ["2026-11-20"]
    assert [run["date"] for run in athlete["prior_runs"]] == ["2026-11-18"]
    assert athlete["stored_analyses"][0]["activity_date"] == "2026-11-20"
    assert athlete["workouts_after_brief_date"][0]["title"] == "Drills/hill strides"
    assert "hrv" in athlete["data_not_stored"]
    assert "recent_runs" not in athlete
