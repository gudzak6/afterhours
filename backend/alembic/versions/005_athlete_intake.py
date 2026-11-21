"""Athlete intake answers from signup, including recent races.

Revision ID: 005_athlete_intake
Revises: 004_planned_workouts
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_athlete_intake"
down_revision: str | None = "004_planned_workouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "intake" not in _columns("athletes"):
        op.add_column("athletes", sa.Column("intake", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "intake" in _columns("athletes"):
        with op.batch_alter_table("athletes") as batch:
            batch.drop_column("intake")
