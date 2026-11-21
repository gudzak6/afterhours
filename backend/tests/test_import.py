"""Mapping and import rules that do not call Garmin."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.garmin.mapping import normalize_activity, pace_seconds_per_mile
from app.models import Activity, Athlete
from app.security import redact_secrets
from app.services.mileage import window_stats
from app.services.sync import _upsert_activity


def test_missing_measurement_stays_missing_and_zero_stays_zero() -> None:
    mapped = normalize_activity(
        {
            "activityId": 42,
            "activityName": "Easy",
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-11-09 12:00:00",
            "startTimeLocal": "2026-11-09 07:00:00",
            "distance": 11812.3,
            "duration": 3689.0,
            "movingDuration": 3600.0,
            "elapsedDuration": 3689000.0,
            "averageSpeed": 3.2,
            "averageHR": None,
            "averageRunningCadenceInStepsPerMinute": 0,
        }
    )
    assert mapped["average_heart_rate_bpm"] is None
    assert "average_heart_rate_bpm" not in mapped["present_fields"]
    assert mapped["average_cadence_spm"] == 0
    assert "average_cadence_spm" in mapped["present_fields"]
    assert mapped["elapsed_duration_raw"] == 3689000.0
    assert mapped["duration_seconds"] == 3689.0
    assert mapped["start_time_utc"] == datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    assert mapped["average_pace_seconds_per_mile"] == pace_seconds_per_mile(3.2)


def test_zero_speed_does_not_invent_a_pace() -> None:
    assert pace_seconds_per_mile(0) is None
    assert pace_seconds_per_mile(None) is None
    assert pace_seconds_per_mile(3.2) > 0


def test_redact_secrets_removes_tokens() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payloadvalue.signaturevalue and ApiKey super-secret-value"
    cleaned = redact_secrets(text)
    assert "super-secret-value" not in cleaned
    assert "eyJhbGciOi" not in cleaned
    assert "[redacted]" in cleaned


def test_mileage_window_accepts_naive_timestamps() -> None:
    class Row:
        def __init__(self, start: datetime, distance: float) -> None:
            self.start_time_utc = start
            self.distance_meters = distance

    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    recent = Row(datetime(2026, 11, 9, 16, 31, 13), 11812.3)
    old = Row(datetime(2026, 10, 1, 12, 0, 0), 5000.0)
    count, with_distance, meters = window_stats([recent, old], now=now, days=7)
    assert count == 1
    assert with_distance == 1
    assert meters == 11812.3


def test_duplicate_garmin_id_updates_the_same_row() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(UTC)
        athlete = Athlete(display_name="Athlete", created_at=now, updated_at=now)
        session.add(athlete)
        session.commit()
        first = {
            "activityId": 99,
            "activityName": "Morning Run",
            "distance": 5000,
            "duration": 1800,
            "averageSpeed": 2.8,
            "startTimeGMT": "2026-11-09 12:00:00",
        }
        assert _upsert_activity(session, athlete, first) == "imported"
        session.commit()
        second = {**first, "activityName": "Morning Run updated", "averageHR": 140}
        assert _upsert_activity(session, athlete, second) == "updated"
        session.commit()
        count = session.scalar(select(func.count()).select_from(Activity))
        stored = session.scalar(select(Activity))
        assert count == 1
        assert stored is not None
        assert stored.name == "Morning Run updated"
        assert stored.average_heart_rate_bpm == 140
        assert stored.garmin_activity_id == 99
