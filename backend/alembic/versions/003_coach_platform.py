"""Coach roster, plans, briefs, and email delivery.

Revision ID: 003_coach_platform
Revises: 002_fit_details
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "003_coach_platform"
down_revision: str | None = "002_fit_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "coaches" not in _tables():
        op.create_table(
            "coaches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("email", sa.String(length=200), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    athlete_columns = _columns("athletes")
    for column in (
        sa.Column("coach_id", sa.Integer(), nullable=True),
        sa.Column("target_time", sa.String(length=40), nullable=True),
        sa.Column("coach_notes", sa.Text(), nullable=True),
    ):
        if column.name not in athlete_columns:
            op.add_column("athletes", column)
    now = datetime.now(UTC)
    op.execute(
        sa.text(
            "INSERT INTO coaches (display_name, timezone, email_notifications_enabled, created_at, updated_at) "
            "SELECT 'Coach', 'America/New_York', 0, :now, :now WHERE NOT EXISTS (SELECT 1 FROM coaches)"
        ).bindparams(now=now)
    )
    op.execute(sa.text("UPDATE athletes SET coach_id = (SELECT id FROM coaches ORDER BY id LIMIT 1) WHERE coach_id IS NULL"))
    if "scheduled_workouts" in _tables():
        return
    op.create_table(
        "scheduled_workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scheduled_workouts_athlete", "scheduled_workouts", ["athlete_id"])
    op.create_table(
        "coaching_briefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("recipient", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_deliveries")
    op.drop_table("coaching_briefs")
    op.drop_index("ix_scheduled_workouts_athlete", table_name="scheduled_workouts")
    op.drop_table("scheduled_workouts")
    with op.batch_alter_table("athletes") as batch:
        batch.drop_column("coach_notes")
        batch.drop_column("target_time")
        batch.drop_column("coach_id")
    op.drop_table("coaches")
