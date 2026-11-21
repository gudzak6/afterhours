"""Structured prescriptions, plan edits, and manual workout matches.

Revision ID: 004_planned_workouts
Revises: 003_coach_platform
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_planned_workouts"
down_revision: str | None = "003_coach_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _columns("scheduled_workouts")
    additions = [
        sa.Column("workout_type", sa.String(length=40), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("warmup", sa.Text(), nullable=True),
        sa.Column("cooldown", sa.Text(), nullable=True),
        sa.Column("repetitions", sa.Integer(), nullable=True),
        sa.Column("rep_distance_meters", sa.Float(), nullable=True),
        sa.Column("recovery_seconds", sa.Float(), nullable=True),
        sa.Column("target_pace_seconds_per_mile", sa.Float(), nullable=True),
        sa.Column("intensity", sa.String(length=80), nullable=True),
        sa.Column("coach_notes", sa.Text(), nullable=True),
        sa.Column("original_prescription", sa.JSON(), nullable=True),
        sa.Column("match_activity_id", sa.Integer(), nullable=True),
        sa.Column("match_source", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in additions:
        if column.name not in existing:
            op.add_column("scheduled_workouts", column)
    if "plan_revisions" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "plan_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scheduled_workout_id", sa.Integer(), sa.ForeignKey("scheduled_workouts.id"), nullable=False),
            sa.Column("prescription", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("plan_revisions")
    with op.batch_alter_table("scheduled_workouts") as batch:
        for name in (
            "updated_at",
            "match_source",
            "match_activity_id",
            "original_prescription",
            "coach_notes",
            "intensity",
            "target_pace_seconds_per_mile",
            "recovery_seconds",
            "rep_distance_meters",
            "repetitions",
            "cooldown",
            "warmup",
            "distance_meters",
            "workout_type",
        ):
            batch.drop_column(name)
