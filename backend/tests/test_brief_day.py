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


def test_upcoming_brief_keeps_only_the_plan():
    payload = prepare_brief_payload(
        date(2026, 11, 23),
        date(2026, 11, 21),
        [
            {
                "athlete_id": 4,
                "athlete_name": "Joey",
                "attention_reasons": ["4 confirmed missed sessions"],
                "recent_activity": "New York Running · 8.12 mi",
                "stored_summary": "Controlled aerobic execution.",
            }
        ],
        {4: [{"title": "Drills/hill strides", "detail": "5.00 mi"}]},
    )
    assert payload["day_relation"] == "upcoming"
    athlete = payload["roster"][0]
    assert athlete["planned_for_brief_date"] == [{"title": "Drills/hill strides", "detail": "5.00 mi"}]
    assert "attention_reasons" not in athlete
    assert "stored_summary" not in athlete
    assert athlete["earlier_activity"] == "New York Running · 8.12 mi"
