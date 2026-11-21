"""Store an athlete Garmin sign-in separately from the coach API key.

Revision ID: 007_garmin_sign_in
Revises: 006_athlete_portal
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_garmin_sign_in"
down_revision: str | None = "006_athlete_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    columns = _columns("garmin_connections")
    if "garmin_email" not in columns:
        op.add_column("garmin_connections", sa.Column("garmin_email", sa.String(320), nullable=True))
    if "connect_token" not in columns:
        op.add_column("garmin_connections", sa.Column("connect_token", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = _columns("garmin_connections")
    if "connect_token" in columns:
        op.drop_column("garmin_connections", "connect_token")
    if "garmin_email" in columns:
        op.drop_column("garmin_connections", "garmin_email")
