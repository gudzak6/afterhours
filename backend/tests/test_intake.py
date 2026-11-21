"""Signup intake, including recent race goals and result times, stays on the athlete."""

from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import apply_athlete_update
from app.config import get_settings
from app.database import Base
from app.models import Athlete
from app.schemas import AthleteIntake, AthleteUpdate, RecentRace


def test_intake_and_recent_races_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    settings = get_settings()
    with Session(engine) as session:
        athlete = Athlete(display_name="Athlete", created_at=now, updated_at=now)
        session.add(athlete)
        session.commit()

        updated = apply_athlete_update(
            session,
            settings,
            athlete,
            AthleteUpdate(
                intake=AthleteIntake(
                    first_name="Jordan",
                    last_name="Lee",
                    email="jordan@example.com",
                    phone="555-0100",
                    events="Chicago Marathon",
                    outcome_goals="Sub-3 marathon",
                    process_goals="Stay healthy through the build",
                    personal_bests="5K 18:40",
                    weekly_miles_last_3_weeks="40",
                    weekly_miles_last_3_months="35",
                    training_stipulations="No workouts on Wednesday",
                    training_style="Mixture of strength and speed",
                    strengths="Consistency",
                    weaknesses="Downhill pace",
                    why_run="I like racing",
                    preferred_coach="Alex",
                    anything_else="Morning runner",
                    heard_about_us="A friend",
                    recent_races=[
                        RecentRace(),
                        RecentRace(
                            event="Boston Marathon",
                            race_date=date(2026, 4, 20),
                            goal_time="2:55:00",
                            result_time="2:58:12",
                        ),
                    ],
                )
            ),
        )

        assert updated.display_name == "Jordan Lee"
        assert updated.intake.email == "jordan@example.com"
        assert updated.intake.events == "Chicago Marathon"
        assert len(updated.intake.recent_races) == 1
        race = updated.intake.recent_races[0]
        assert race.event == "Boston Marathon"
        assert race.race_date == date(2026, 4, 20)
        assert race.goal_time == "2:55:00"
        assert race.result_time == "2:58:12"

        kept = apply_athlete_update(
            session,
            settings,
            athlete,
            AthleteUpdate(coach_notes="Follow up on the downhill."),
        )
        assert kept.coach_notes == "Follow up on the downhill."
        assert kept.intake.recent_races[0].result_time == "2:58:12"
        assert kept.display_name == "Jordan Lee"
