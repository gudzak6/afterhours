"""Store running power from FIT records.

Revision ID: 008_sample_power
Revises: 007_garmin_sign_in
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_sample_power"
down_revision: str | None = "007_garmin_sign_in"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_samples", sa.Column("power_watts", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("activity_samples", "power_watts")
