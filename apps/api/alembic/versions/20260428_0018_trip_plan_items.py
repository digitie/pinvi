"""add trip plan item resource links

Revision ID: 20260428_0018
Revises: 20260428_0017
Create Date: 2026-04-28 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0018"
down_revision: str | None = "20260428_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_day_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("festival_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_key", sa.String(length=180), nullable=True),
        sa.Column("title_snapshot", sa.String(length=255), nullable=False),
        sa.Column("address_snapshot", sa.String(length=700), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operating_hours_snapshot", sa.String(length=255), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("resource_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('place', 'festival', 'trail', 'scenic_road', 'route', 'custom')",
            name="ck_tpi_resource_type",
        ),
        sa.CheckConstraint("sort_order >= 1", name="ck_tpi_positive_sort_order"),
        sa.CheckConstraint(
            "place_id IS NULL OR resource_type = 'place'",
            name="ck_tpi_place_type_match",
        ),
        sa.CheckConstraint(
            "festival_id IS NULL OR resource_type = 'festival'",
            name="ck_tpi_festival_type_match",
        ),
        sa.CheckConstraint(
            "NOT (place_id IS NOT NULL AND festival_id IS NOT NULL)",
            name="ck_tpi_single_fk_resource",
        ),
        sa.CheckConstraint(
            "resource_key IS NULL OR resource_type IN ('trail', 'scenic_road', 'route', 'custom')",
            name="ck_tpi_resource_key_type",
        ),
        sa.ForeignKeyConstraint(
            ["festival_id"],
            ["tour_serving_public_cultural_festival.id"],
            name="fk_tpi_festival_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_tpi_place_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trip_day_id"],
            ["trip_days.id"],
            name="fk_tpi_trip_day_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trip_plan_items"),
        sa.UniqueConstraint("trip_day_id", "sort_order", name="uq_tpi_day_sort_order"),
    )
    op.create_index("ix_tpi_trip_day_sort", "trip_plan_items", ["trip_day_id", "sort_order"])
    op.create_index("ix_tpi_place_id", "trip_plan_items", ["place_id"])
    op.create_index("ix_tpi_festival_id", "trip_plan_items", ["festival_id"])
    op.create_index("ix_tpi_resource_type", "trip_plan_items", ["resource_type"])


def downgrade() -> None:
    op.drop_index("ix_tpi_resource_type", table_name="trip_plan_items")
    op.drop_index("ix_tpi_festival_id", table_name="trip_plan_items")
    op.drop_index("ix_tpi_place_id", table_name="trip_plan_items")
    op.drop_index("ix_tpi_trip_day_sort", table_name="trip_plan_items")
    op.drop_table("trip_plan_items")
