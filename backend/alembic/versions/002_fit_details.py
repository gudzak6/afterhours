"""FIT summary and workout steps.

Revision ID: 002_fit_details
Revises: 001_initial
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_fit_details"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("fit_summary", sa.JSON(), nullable=True))
    op.create_table(
        "activity_workout_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("intensity", sa.String(length=40), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_low", sa.Float(), nullable=True),
        sa.Column("target_high", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("present_fields", sa.JSON(), nullable=False),
        sa.Column("raw_step", sa.JSON(), nullable=False),
        sa.UniqueConstraint("activity_id", "step_index", name="uq_activity_steps_index"),
    )
    op.create_index("ix_activity_steps_activity", "activity_workout_steps", ["activity_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_steps_activity", table_name="activity_workout_steps")
    op.drop_table("activity_workout_steps")
    op.drop_column("activities", "fit_summary")
