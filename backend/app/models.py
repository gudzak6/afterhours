"""Normalized tables. Milestone 1 writes athletes, connections, sync jobs, and activities."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Coach(Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("coaches.id"))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_time: Mapped[str | None] = mapped_column(String(40))
    coach_notes: Mapped[str | None] = mapped_column(Text)
    running_experience: Mapped[str | None] = mapped_column(String(80))
    typical_weekly_mileage: Mapped[float | None] = mapped_column(Float)
    preferred_training_days: Mapped[list | None] = mapped_column(JSON)
    workout_preferences: Mapped[dict | None] = mapped_column(JSON)
    max_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    intake: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    activities: Mapped[list[Activity]] = relationship(back_populates="athlete")


class GarminConnection(Base):
    __tablename__ = "garmin_connections"
    __table_args__ = (UniqueConstraint("athlete_id", name="uq_garmin_connections_athlete"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    personal_api_key: Mapped[str | None] = mapped_column(Text)
    garmin_email: Mapped[str | None] = mapped_column(String(320))
    connect_token: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrainingGoal(Base):
    __tablename__ = "training_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    primary_race_goal: Mapped[str | None] = mapped_column(String(200))
    goal_race_date: Mapped[date | None] = mapped_column(Date)
    personal_records: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AthleteThreshold(Base):
    __tablename__ = "athlete_thresholds"
    __table_args__ = (UniqueConstraint("athlete_id", "name", name="uq_athlete_threshold_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    pace_seconds_per_mile: Mapped[float | None] = mapped_column(Float)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScheduledWorkout(Base):
    __tablename__ = "scheduled_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    workout_type: Mapped[str | None] = mapped_column(String(40))
    distance_meters: Mapped[float | None] = mapped_column(Float)
    warmup: Mapped[str | None] = mapped_column(Text)
    cooldown: Mapped[str | None] = mapped_column(Text)
    repetitions: Mapped[int | None] = mapped_column(Integer)
    rep_distance_meters: Mapped[float | None] = mapped_column(Float)
    recovery_seconds: Mapped[float | None] = mapped_column(Float)
    target_pace_seconds_per_mile: Mapped[float | None] = mapped_column(Float)
    intensity: Mapped[str | None] = mapped_column(String(80))
    coach_notes: Mapped[str | None] = mapped_column(Text)
    original_prescription: Mapped[dict | None] = mapped_column(JSON)
    match_activity_id: Mapped[int | None] = mapped_column(Integer)
    match_source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanRevision(Base):
    __tablename__ = "plan_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheduled_workout_id: Mapped[int] = mapped_column(ForeignKey("scheduled_workouts.id"), nullable=False)
    prescription: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CoachingBrief(Base):
    __tablename__ = "coaching_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False)
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    report: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False)
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lookback_days: Mapped[int | None] = mapped_column(Integer)
    activities_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activities_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activities_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activities_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("athlete_id", "garmin_activity_id", name="uq_activities_garmin_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    garmin_activity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(300))
    activity_type_key: Mapped[str | None] = mapped_column(String(80))
    start_time_local: Mapped[str | None] = mapped_column(String(40))
    start_time_gmt: Mapped[str | None] = mapped_column(String(40))
    start_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distance_meters: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    moving_duration_seconds: Mapped[float | None] = mapped_column(Float)
    elapsed_duration_raw: Mapped[float | None] = mapped_column(Float)
    average_speed_mps: Mapped[float | None] = mapped_column(Float)
    max_speed_mps: Mapped[float | None] = mapped_column(Float)
    average_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    max_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    elevation_gain_meters: Mapped[float | None] = mapped_column(Float)
    elevation_loss_meters: Mapped[float | None] = mapped_column(Float)
    average_cadence_spm: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    lap_count: Mapped[int | None] = mapped_column(Integer)
    start_latitude: Mapped[float | None] = mapped_column(Float)
    start_longitude: Mapped[float | None] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(300))
    manual_activity: Mapped[bool | None] = mapped_column(Boolean)
    present_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    raw_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    athlete_overrides: Mapped[dict | None] = mapped_column(JSON)
    fit_summary: Mapped[dict | None] = mapped_column(JSON)
    import_status: Mapped[str] = mapped_column(String(32), nullable=False, default="summary_only")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    athlete: Mapped[Athlete] = relationship(back_populates="activities")


class ActivityFile(Base):
    __tablename__ = "activity_files"
    __table_args__ = (UniqueConstraint("activity_id", "kind", name="uq_activity_files_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActivityLap(Base):
    __tablename__ = "activity_laps"
    __table_args__ = (UniqueConstraint("activity_id", "lap_number", name="uq_activity_laps_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    lap_number: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    average_speed_mps: Mapped[float | None] = mapped_column(Float)
    average_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    max_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    average_cadence_spm: Mapped[float | None] = mapped_column(Float)
    start_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    present_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    raw_lap: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivityWorkoutStep(Base):
    __tablename__ = "activity_workout_steps"
    __table_args__ = (UniqueConstraint("activity_id", "step_index", name="uq_activity_steps_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity: Mapped[str | None] = mapped_column(String(40))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_low: Mapped[float | None] = mapped_column(Float)
    target_high: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    present_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    raw_step: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivitySample(Base):
    __tablename__ = "activity_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    sample_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[float | None] = mapped_column(Float)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    cadence_spm: Mapped[float | None] = mapped_column(Float)
    altitude_meters: Mapped[float | None] = mapped_column(Float)
    power_watts: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    present_fields: Mapped[list] = mapped_column(JSON, nullable=False)


class WorkoutSegment(Base):
    __tablename__ = "workout_segments"
    __table_args__ = (UniqueConstraint("activity_id", "segment_index", name="uq_workout_segments_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    start_lap: Mapped[int | None] = mapped_column(Integer)
    end_lap: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class WorkoutClassification(Base):
    __tablename__ = "workout_classifications"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_workout_classifications_activity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    workout_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    uncertainty: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutAnalysis(Base):
    __tablename__ = "workout_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    report: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_trace: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Race(Base):
    __tablename__ = "races"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    race_date: Mapped[date | None] = mapped_column(Date)
    distance_label: Mapped[str | None] = mapped_column(String(80))
    distance_meters: Mapped[float | None] = mapped_column(Float)
    goal_time: Mapped[str | None] = mapped_column(String(40))
    result_time: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutFeedback(Base):
    __tablename__ = "workout_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    scheduled_workout_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_workouts.id"))
    rpe: Mapped[int | None] = mapped_column(Integer)
    fatigue: Mapped[int | None] = mapped_column(Integer)
    soreness: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkoutComment(Base):
    __tablename__ = "workout_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    scheduled_workout_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_workouts.id"))
    author: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CoachMessage(Base):
    __tablename__ = "coach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    author: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LactateReading(Base):
    __tablename__ = "lactate_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), nullable=False)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    mmol: Mapped[float] = mapped_column(Float, nullable=False)
    pace_seconds_per_mile: Mapped[float | None] = mapped_column(Float)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
