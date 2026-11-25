"""Athlete portal records stay on the same athlete the coach already sees."""

import json
from datetime import UTC, date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base
from app.models import Activity, Athlete, GarminConnection, Race
from app.schemas import AthleteIntake
from app.services.portal import (
    PortalInputError,
    add_message,
    analytics,
    edit_activity,
    join_athlete,
    log_manual,
    race_predictions,
    garmin_state,
    save_feedback,
    save_garmin_login,
    save_race,
    save_workout_account,
)
from app.services.sync import reapply_athlete_overrides


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _intake(**overrides) -> AthleteIntake:
    payload = {
        "first_name": "Jordan",
        "last_name": "Lee",
        "email": "jordan@example.com",
        "phone": "555-0100",
        "events": "Chicago Marathon",
        "outcome_goals": "Sub-3 marathon",
        "process_goals": "Stay healthy",
        "personal_bests": "5K 18:40",
        "weekly_miles_last_3_weeks": "40",
        "weekly_miles_last_3_months": "35",
        "training_stipulations": "Mondays off",
        "training_style": "A mix of strength and speed",
        "strengths": "Consistency",
        "weaknesses": "Patience",
        "why_run": "The long run",
        "preferred_coach": "Anyone on the team",
    }
    payload.update(overrides)
    return AthleteIntake(**payload)


def test_join_requires_the_public_intake_and_updates_the_same_email() -> None:
    settings = get_settings()
    with _session() as session:
        try:
            join_athlete(session, settings, _intake(email=""))
        except PortalInputError as exc:
            assert "Email" in str(exc)
        else:
            raise AssertionError("blank email was accepted")

        athlete = join_athlete(session, settings, _intake())
        assert athlete.display_name == "Jordan Lee"
        again = join_athlete(session, settings, _intake(events="Boston Marathon"))
        assert again.id == athlete.id
        assert again.intake["events"] == "Boston Marathon"
        assert session.scalars(select(Athlete)).all().__len__() == 1


def test_manual_edits_survive_a_later_garmin_overwrite() -> None:
    settings = get_settings()
    with _session() as session:
        athlete = join_athlete(session, settings, _intake())
        logged = log_manual(
            session,
            athlete,
            name="Easy",
            start_day=date(2026, 11, 18),
            start_time="07:30",
            distance_miles=6,
            duration_seconds=3600,
            heart_rate=140,
            notes="Legs felt fine",
            workout_type="easy",
        )
        assert logged["manual"] is True
        assert logged["garmin_activity_id"] < 0
        edited = edit_activity(
            session,
            athlete,
            logged["garmin_activity_id"],
            changes={"distance_miles": 6.2, "notes": "Added the cooldown"},
        )
        assert edited["distance_miles"] == 6.2
        stored = session.scalar(select(Activity).where(Activity.athlete_id == athlete.id))
        stored.distance_meters = 1000
        reapply_athlete_overrides(stored)
        assert stored.distance_meters == 6.2 * 1609.344


def test_an_athletes_account_is_stored_and_kept_after_the_file_changes() -> None:
    def complete(_settings, **_kwargs):
        return json.dumps(
            {
                "summary": "The treadmill pace was off. Six 800s were at 6:30 with 90 seconds easy.",
                "distance_miles": 6.1,
                "duration_seconds": None,
                "average_heart_rate_bpm": None,
                "splits": [{"label": "800m rep", "distance_miles": 0.5, "duration_seconds": 195, "pace": "6:30"}],
            }
        )

    with _session() as session:
        athlete = join_athlete(session, get_settings(), _intake())
        logged = log_manual(
            session,
            athlete,
            name="Treadmill",
            start_day=date(2026, 11, 24),
            start_time="06:00",
            distance_miles=5,
            duration_seconds=3000,
            heart_rate=150,
            notes=None,
            workout_type="intervals",
        )
        saved = save_workout_account(
            session,
            get_settings(),
            athlete,
            logged["garmin_activity_id"],
            "The treadmill pace was off. I ran 6x800 at 6:30 with 90 seconds easy, 6.1 miles.",
            complete=complete,
        )
        assert saved["distance_miles"] == 6.1
        assert saved["account"]["splits"][0]["pace"] == "6:30"
        assert "treadmill" in saved["notes"].lower()
        stored = session.scalar(select(Activity).where(Activity.athlete_id == athlete.id))
        stored.distance_meters = 1000
        reapply_athlete_overrides(stored)
        assert stored.distance_meters == 6.1 * 1609.344


def test_feedback_race_prediction_and_message() -> None:
    settings = get_settings()
    with _session() as session:
        athlete = join_athlete(session, settings, _intake())
        logged = log_manual(
            session,
            athlete,
            name="Tempo",
            start_day=date(2026, 11, 19),
            start_time="06:00",
            distance_miles=8,
            duration_seconds=3600,
            heart_rate=160,
            notes=None,
            workout_type="tempo",
        )
        feedback = save_feedback(
            session,
            athlete,
            scheduled_workout_id=None,
            garmin_activity_id=logged["garmin_activity_id"],
            rpe=7,
            fatigue=3,
            soreness=2,
            comment="Smooth",
        )
        assert feedback["rpe"] == 7
        race = save_race(
            session,
            athlete,
            {
                "name": "Local 5K",
                "race_date": date(2026, 10, 1),
                "distance_label": "5K",
                "distance_meters": None,
                "goal_time": "19:00",
                "result_time": "20:00",
                "notes": None,
            },
        )
        assert race["distance_meters"] == 5000
        stored = session.scalars(select(Race).where(Race.athlete_id == athlete.id)).all()
        predicted = race_predictions(stored)
        ten_k = next(item for item in predicted["estimates"] if item["label"] == "10K")
        assert ten_k["time"].startswith("41:")
        sent = add_message(session, athlete, author="athlete", body="Can we keep Monday easy?")
        assert sent["author"] == "athlete"
        report = analytics(session, settings, athlete)
        assert report["predictions"]["source"]["name"] == "Local 5K"
        assert report["weekly_mileage"]


def test_garmin_sign_in_stores_a_session_and_not_the_password(monkeypatch) -> None:
    password = "garmin-password-should-not-be-stored"
    monkeypatch.setattr("app.garmin.connect.sign_in_garmin", lambda athlete_id, email, password, mfa_code=None: "opaque-session")
    now = datetime.now(UTC)
    with _session() as session:
        athlete = Athlete(display_name="Jordan", created_at=now, updated_at=now)
        session.add(athlete)
        session.commit()
        token = save_garmin_login(session, athlete, "runner@example.com", password, None)
        connection = session.scalar(select(GarminConnection).where(GarminConnection.athlete_id == athlete.id))
        assert token == "opaque-session"
        assert connection is not None
        assert connection.connect_token == "opaque-session"
        assert connection.garmin_email == "runner@example.com"
        assert connection.personal_api_key is None
        assert password not in f"{connection.connect_token} {connection.garmin_email}"
        state = garmin_state(session, athlete.id)
        assert state["key_saved"] is True
        assert state["connected"] is False
