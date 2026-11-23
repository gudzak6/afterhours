"""Store one Coach's Review paragraph per athlete, day, and source.

Revision ID: 009_coach_reviews
Revises: 008_sample_power
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_coach_reviews"
down_revision: str | None = "008_sample_power"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("paragraph", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("athlete_id", "review_date", "source_key", name="uq_coach_reviews_source"),
    )


def downgrade() -> None:
    op.drop_table("coach_reviews")
