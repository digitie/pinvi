"""trip primary region code

Revision ID: 20260606_0010
Revises: 20260606_0009
Create Date: 2026-06-06 19:30:00

T-141: `region_hint` 자유텍스트와 별개로 지역 기반 알림/질의에 쓸 구조화 code를
Trip 자체에 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_0010"
down_revision: str | None = "20260606_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("primary_region_code", sa.String(length=10), nullable=True),
        schema="app",
    )
    op.add_column(
        "trips",
        sa.Column("primary_region_source", sa.String(length=16), nullable=True),
        schema="app",
    )
    op.create_check_constraint(
        "ck_trips_primary_region_code",
        "trips",
        "primary_region_code IS NULL OR primary_region_code ~ '^[0-9]{2,10}$'",
        schema="app",
    )
    op.create_check_constraint(
        "ck_trips_primary_region_source",
        "trips",
        "primary_region_source IS NULL OR primary_region_source IN "
        "('manual', 'poi_snapshot', 'geocoded')",
        schema="app",
    )
    op.create_check_constraint(
        "ck_trips_primary_region_pair",
        "trips",
        "(primary_region_code IS NULL AND primary_region_source IS NULL) OR "
        "(primary_region_code IS NOT NULL AND primary_region_source IS NOT NULL)",
        schema="app",
    )
    op.create_index(
        "ix_trips_primary_region",
        "trips",
        ["primary_region_code"],
        schema="app",
        postgresql_where=sa.text("primary_region_code IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_trips_primary_region", table_name="trips", schema="app")
    op.drop_constraint("ck_trips_primary_region_pair", "trips", schema="app")
    op.drop_constraint("ck_trips_primary_region_source", "trips", schema="app")
    op.drop_constraint("ck_trips_primary_region_code", "trips", schema="app")
    op.drop_column("trips", "primary_region_source", schema="app")
    op.drop_column("trips", "primary_region_code", schema="app")
