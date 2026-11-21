"""Athlete portal: Garmin keys, races, feedback, messages, and lactate.

Revision ID: 006_athlete_portal
Revises: 005_athlete_intake
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_athlete_portal"
down_revision: str | None = "005_athlete_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "personal_api_key" not in _columns("garmin_connections"):
        op.add_column("garmin_connections", sa.Column("personal_api_key", sa.Text(), nullable=True))
    if "athlete_overrides" not in _columns("activities"):
        op.add_column("activities", sa.Column("athlete_overrides", sa.JSON(), nullable=True))
    tables = _tables()
    if "races" not in tables:
        op.create_table(
            "races",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("race_date", sa.Date(), nullable=True),
            sa.Column("distance_label", sa.String(80), nullable=True),
            sa.Column("distance_meters", sa.Float(), nullable=True),
            sa.Column("goal_time", sa.String(40), nullable=True),
            sa.Column("result_time", sa.String(40), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "workout_feedback" not in tables:
        op.create_table(
            "workout_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
            sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=True),
            sa.Column("scheduled_workout_id", sa.Integer(), sa.ForeignKey("scheduled_workouts.id"), nullable=True),
            sa.Column("rpe", sa.Integer(), nullable=True),
            sa.Column("fatigue", sa.Integer(), nullable=True),
            sa.Column("soreness", sa.Integer(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "workout_comments" not in tables:
        op.create_table(
            "workout_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
            sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=True),
            sa.Column("scheduled_workout_id", sa.Integer(), sa.ForeignKey("scheduled_workouts.id"), nullable=True),
            sa.Column("author", sa.String(20), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "coach_messages" not in tables:
        op.create_table(
            "coach_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
            sa.Column("author", sa.String(20), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "lactate_readings" not in tables:
        op.create_table(
            "lactate_readings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
            sa.Column("measured_on", sa.Date(), nullable=False),
            sa.Column("mmol", sa.Float(), nullable=False),
            sa.Column("pace_seconds_per_mile", sa.Float(), nullable=True),
            sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    for table in ("lactate_readings", "coach_messages", "workout_comments", "workout_feedback", "races"):
        if table in _tables():
            op.drop_table(table)
    if "athlete_overrides" in _columns("activities"):
        with op.batch_alter_table("activities") as batch:
            batch.drop_column("athlete_overrides")
    if "personal_api_key" in _columns("garmin_connections"):
        with op.batch_alter_table("garmin_connections") as batch:
            batch.drop_column("personal_api_key")
