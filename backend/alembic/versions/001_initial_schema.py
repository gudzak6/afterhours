"""Initial schema for athletes, Garmin sync, activities, and future coaching tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "athletes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("running_experience", sa.String(length=80), nullable=True),
        sa.Column("typical_weekly_mileage", sa.Float(), nullable=True),
        sa.Column("preferred_training_days", sa.JSON(), nullable=True),
        sa.Column("workout_preferences", sa.JSON(), nullable=True),
        sa.Column("max_heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "garmin_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("athlete_id", name="uq_garmin_connections_athlete"),
    )

    op.create_table(
        "training_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("primary_race_goal", sa.String(length=200), nullable=True),
        sa.Column("goal_race_date", sa.Date(), nullable=True),
        sa.Column("personal_records", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_training_goals_athlete", "training_goals", ["athlete_id"])

    op.create_table(
        "athlete_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("pace_seconds_per_mile", sa.Float(), nullable=True),
        sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("athlete_id", "name", name="uq_athlete_threshold_name"),
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("activities_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activities_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activities_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activities_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
    )
    op.create_index("ix_sync_jobs_athlete_started", "sync_jobs", ["athlete_id", "started_at"])

    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("garmin_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=True),
        sa.Column("activity_type_key", sa.String(length=80), nullable=True),
        sa.Column("start_time_local", sa.String(length=40), nullable=True),
        sa.Column("start_time_gmt", sa.String(length=40), nullable=True),
        sa.Column("start_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("moving_duration_seconds", sa.Float(), nullable=True),
        sa.Column("elapsed_duration_raw", sa.Float(), nullable=True),
        sa.Column("average_speed_mps", sa.Float(), nullable=True),
        sa.Column("max_speed_mps", sa.Float(), nullable=True),
        sa.Column("average_heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("max_heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("elevation_gain_meters", sa.Float(), nullable=True),
        sa.Column("elevation_loss_meters", sa.Float(), nullable=True),
        sa.Column("average_cadence_spm", sa.Float(), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("lap_count", sa.Integer(), nullable=True),
        sa.Column("start_latitude", sa.Float(), nullable=True),
        sa.Column("start_longitude", sa.Float(), nullable=True),
        sa.Column("location_name", sa.String(length=300), nullable=True),
        sa.Column("manual_activity", sa.Boolean(), nullable=True),
        sa.Column("present_fields", sa.JSON(), nullable=False),
        sa.Column("raw_summary", sa.JSON(), nullable=False),
        sa.Column("import_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("athlete_id", "garmin_activity_id", name="uq_activities_garmin_id"),
    )
    op.create_index("ix_activities_athlete_start", "activities", ["athlete_id", "start_time_utc"])
    op.create_index("ix_activities_type", "activities", ["activity_type_key"])

    op.create_table(
        "activity_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("activity_id", "kind", name="uq_activity_files_kind"),
    )

    op.create_table(
        "activity_laps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("average_speed_mps", sa.Float(), nullable=True),
        sa.Column("average_heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("max_heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("average_cadence_spm", sa.Float(), nullable=True),
        sa.Column("start_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("present_fields", sa.JSON(), nullable=False),
        sa.Column("raw_lap", sa.JSON(), nullable=False),
        sa.UniqueConstraint("activity_id", "lap_number", name="uq_activity_laps_number"),
    )
    op.create_index("ix_activity_laps_activity", "activity_laps", ["activity_id"])

    op.create_table(
        "activity_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("sample_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("cadence_spm", sa.Float(), nullable=True),
        sa.Column("altitude_meters", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("present_fields", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_activity_samples_activity_time",
        "activity_samples",
        ["activity_id", "elapsed_seconds"],
    )

    op.create_table(
        "workout_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("start_lap", sa.Integer(), nullable=True),
        sa.Column("end_lap", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("activity_id", "segment_index", name="uq_workout_segments_index"),
    )

    op.create_table(
        "workout_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("workout_type", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("activity_id", name="uq_workout_classifications_activity"),
    )

    op.create_table(
        "workout_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workout_analyses_activity", "workout_analyses", ["activity_id"])

    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_conversations_athlete", "ai_conversations", ["athlete_id"])

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("ai_conversations.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_trace", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_messages_conversation", "ai_messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("workout_analyses")
    op.drop_table("workout_classifications")
    op.drop_table("workout_segments")
    op.drop_table("activity_samples")
    op.drop_table("activity_laps")
    op.drop_table("activity_files")
    op.drop_table("activities")
    op.drop_table("sync_jobs")
    op.drop_table("athlete_thresholds")
    op.drop_table("training_goals")
    op.drop_table("garmin_connections")
    op.drop_table("athletes")
