"""trip telegram target link

Revision ID: 20260610_0020
Revises: 20260610_0019
Create Date: 2026-06-10 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260610_0020"
down_revision: str | None = "20260610_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip_telegram_targets",
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("trip_id", "telegram_target_id", name="pk_trip_telegram_targets"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_telegram_targets_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_target_id"],
            ["app.telegram_targets.id"],
            name="fk_trip_telegram_targets_target_id",
            ondelete="CASCADE",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_telegram_targets_target",
        "trip_telegram_targets",
        ["telegram_target_id"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trip_telegram_targets_target", table_name="trip_telegram_targets", schema="app"
    )
    op.drop_table("trip_telegram_targets", schema="app")
