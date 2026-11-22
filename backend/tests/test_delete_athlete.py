"""Removing an athlete deletes their records and leaves the rest of the roster."""

from datetime import UTC, date, datetime

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Activity,
    ActivityLap,
    AiConversation,
    AiMessage,
    Athlete,
    AthleteThreshold,
    GarminConnection,
    PlanRevision,
    ScheduledWorkout,
    SyncJob,
    TrainingGoal,
    WorkoutFeedback,
)
from app.services.athletes import delete_athlete


def test_delete_athlete_removes_their_records_only() -> None:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        keeper = Athlete(display_name="Keeper", created_at=now, updated_at=now)
        removed = Athlete(display_name="Removed", created_at=now, updated_at=now)
        session.add_all([keeper, removed])
        session.commit()
        activity = Activity(
            athlete_id=removed.id,
            garmin_activity_id=42,
            present_fields=[],
            raw_summary={},
            created_at=now,
            updated_at=now,
        )
        kept_activity = Activity(
            athlete_id=keeper.id,
            garmin_activity_id=43,
            present_fields=[],
            raw_summary={},
            created_at=now,
            updated_at=now,
        )
        session.add_all([activity, kept_activity])
        session.commit()
        session.add(ActivityLap(activity_id=activity.id, lap_number=1, present_fields=[], raw_lap={}))
        session.add(WorkoutFeedback(athlete_id=removed.id, activity_id=activity.id, comment="Easy", updated_at=now))
        workout = ScheduledWorkout(
            athlete_id=removed.id,
            scheduled_date=date(2026, 11, 11),
            title="Easy",
            created_at=now,
        )
        session.add(workout)
        session.commit()
        session.add(PlanRevision(scheduled_workout_id=workout.id, prescription={"title": "Easy"}, created_at=now))
        session.add(GarminConnection(athlete_id=removed.id, status="not_connected", updated_at=now))
        session.add(TrainingGoal(athlete_id=removed.id, primary_race_goal="Marathon", updated_at=now))
        session.add(AthleteThreshold(athlete_id=removed.id, name="LT2", source="coach", updated_at=now))
        session.add(SyncJob(athlete_id=removed.id, trigger="manual", status="succeeded", started_at=now))
        conversation = AiConversation(athlete_id=removed.id, activity_id=activity.id, created_at=now)
        session.add(conversation)
        session.commit()
        session.add(AiMessage(conversation_id=conversation.id, role="user", content="How did it go?", created_at=now))
        session.commit()

        delete_athlete(session, removed)

        assert session.get(Athlete, removed.id) is None
        assert session.get(Athlete, keeper.id) is not None
        assert session.scalar(select(Activity).where(Activity.garmin_activity_id == 42)) is None
        assert session.scalar(select(Activity).where(Activity.garmin_activity_id == 43)) is not None
        assert session.scalars(select(ActivityLap)).all() == []
        assert session.scalars(select(WorkoutFeedback)).all() == []
        assert session.scalars(select(ScheduledWorkout)).all() == []
        assert session.scalars(select(PlanRevision)).all() == []
        assert session.scalars(select(AiMessage)).all() == []
        assert session.scalars(select(GarminConnection)).all() == []
        assert session.scalars(select(TrainingGoal)).all() == []
        assert session.scalars(select(AthleteThreshold)).all() == []
        assert session.scalars(select(SyncJob)).all() == []
