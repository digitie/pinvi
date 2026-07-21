"""dedicated app.trip_day_rise_sets (day-level rise/set, ADR-055 §6)

Revision ID: 20260721_0040
Revises: 20260721_0039
Create Date: 2026-07-21 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from alembic import op

revision: str = "20260721_0040"
down_revision: str | None = "20260721_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR-055 §6: 일자 단위 일출/일몰. 기준 좌표는 그 일자 POI centroid(대표 POI = created_at-earliest).
    # locdate = effective_date. status는 per-POI rise/set과 동일 어휘. ETL asset이 pending_fetch를 채운다.
    op.create_table(
        "trip_day_rise_sets",
        sa.Column("trip_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("locdate", sa.Date(), nullable=True),
        sa.Column("reference_poi_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("reference_label", sa.Text(), nullable=True),
        sa.Column("longitude", sa.Float(precision=53), nullable=True),
        sa.Column("latitude", sa.Float(precision=53), nullable=True),
        sa.Column("sunrise_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sunset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moonrise_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moonset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending_date",
        ),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "raw_payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", JSONB(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trip_id", "day_index", name="pk_trip_day_rise_sets"),
        sa.ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["app.trip_days.trip_id", "app.trip_days.day_index"],
            name="fk_trip_day_rise_sets_day",
            ondelete="CASCADE",
        ),
        schema="app",
    )
    # ETL asset이 채울 대상(status='pending_fetch' 또는 stale)을 빠르게 선택.
    op.create_index(
        "ix_trip_day_rise_sets_fillable",
        "trip_day_rise_sets",
        ["status"],
        schema="app",
        postgresql_where=sa.text("status = 'pending_fetch' OR stale"),
    )


def downgrade() -> None:
    op.drop_index("ix_trip_day_rise_sets_fillable", table_name="trip_day_rise_sets", schema="app")
    op.drop_table("trip_day_rise_sets", schema="app")
