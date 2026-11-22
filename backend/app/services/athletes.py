"""Remove an athlete and the records that belong to them."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import (
    Activity,
    ActivityFile,
    ActivityLap,
    ActivitySample,
    ActivityWorkoutStep,
    AiConversation,
    AiMessage,
    Athlete,
    AthleteThreshold,
    GarminConnection,
    CoachMessage,
    LactateReading,
    PlanRevision,
    Race,
    ScheduledWorkout,
    SyncJob,
    TrainingGoal,
    WorkoutAnalysis,
    WorkoutClassification,
    WorkoutComment,
    WorkoutFeedback,
    WorkoutSegment,
)


def delete_athlete(session: Session, athlete: Athlete) -> None:
    activity_ids = list(session.scalars(select(Activity.id).where(Activity.athlete_id == athlete.id)).all())
    garmin_ids = list(
        session.scalars(select(Activity.garmin_activity_id).where(Activity.athlete_id == athlete.id)).all()
    )
    file_paths = []
    if activity_ids:
        file_paths = list(
            session.scalars(select(ActivityFile.storage_path).where(ActivityFile.activity_id.in_(activity_ids))).all()
        )
    conversation_ids = list(
        session.scalars(select(AiConversation.id).where(AiConversation.athlete_id == athlete.id)).all()
    )
    if activity_ids:
        extra = list(
            session.scalars(select(AiConversation.id).where(AiConversation.activity_id.in_(activity_ids))).all()
        )
        conversation_ids = list(dict.fromkeys([*conversation_ids, *extra]))
    if conversation_ids:
        session.execute(delete(AiMessage).where(AiMessage.conversation_id.in_(conversation_ids)))
        session.execute(delete(AiConversation).where(AiConversation.id.in_(conversation_ids)))
    for model in (WorkoutFeedback, WorkoutComment, CoachMessage, LactateReading, Race):
        session.execute(delete(model).where(model.athlete_id == athlete.id))
    if activity_ids:
        session.execute(delete(WorkoutFeedback).where(WorkoutFeedback.activity_id.in_(activity_ids)))
        session.execute(delete(WorkoutComment).where(WorkoutComment.activity_id.in_(activity_ids)))
        for model in (
            ActivitySample,
            ActivityLap,
            ActivityWorkoutStep,
            ActivityFile,
            WorkoutSegment,
            WorkoutClassification,
            WorkoutAnalysis,
        ):
            session.execute(delete(model).where(model.activity_id.in_(activity_ids)))
        session.execute(delete(Activity).where(Activity.id.in_(activity_ids)))
    workout_ids = list(session.scalars(select(ScheduledWorkout.id).where(ScheduledWorkout.athlete_id == athlete.id)).all())
    if workout_ids:
        session.execute(delete(PlanRevision).where(PlanRevision.scheduled_workout_id.in_(workout_ids)))
    session.execute(delete(ScheduledWorkout).where(ScheduledWorkout.athlete_id == athlete.id))
    for model in (GarminConnection, TrainingGoal, AthleteThreshold, SyncJob):
        session.execute(delete(model).where(model.athlete_id == athlete.id))
    session.delete(athlete)
    session.flush()
    kept_ids = set(
        session.scalars(select(Activity.garmin_activity_id).where(Activity.garmin_activity_id.in_(garmin_ids or [0]))).all()
    )
    kept_paths = set(
        session.scalars(select(ActivityFile.storage_path).where(ActivityFile.storage_path.in_(file_paths or [""]))).all()
    )
    session.commit()
    _remove_files(
        [path for path in file_paths if path not in kept_paths],
        [garmin_id for garmin_id in garmin_ids if garmin_id not in kept_ids],
    )


def _remove_files(file_paths: list[str], garmin_ids: list[int]) -> None:
    for stored in file_paths:
        path = Path(stored)
        if path.is_file():
            path.unlink()
    for garmin_id in garmin_ids:
        folder = DATA_DIR / "raw" / str(garmin_id)
        if folder.is_dir():
            shutil.rmtree(folder)
