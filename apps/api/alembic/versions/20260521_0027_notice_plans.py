"""add admin notice plans

Revision ID: 20260521_0027
Revises: 20260518_0026
Create Date: 2026-05-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260521_0027"
down_revision: str | None = "20260518_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _drop_trip_date_range_constraint()
    op.alter_column("trips", "start_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("trips", "end_date", existing_type=sa.Date(), nullable=True)
    op.create_check_constraint(
        op.f("ck_trips_date_range_order"),
        "trips",
        "(start_date IS NULL AND end_date IS NULL) OR "
        "(start_date IS NOT NULL AND end_date IS NOT NULL AND end_date >= start_date)",
    )
    op.alter_column("trip_days", "date", existing_type=sa.Date(), nullable=True)

    op.create_table(
        "notice_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("source_name", sa.String(length=200)),
        sa.Column("destination", sa.String(length=120)),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(starts_on IS NULL AND ends_on IS NULL) OR "
            "(starts_on IS NOT NULL AND ends_on IS NOT NULL AND ends_on >= starts_on)",
            name="ck_notice_plans_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["users.id"],
            name="fk_notice_plans_created_by_admin_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["users.id"],
            name="fk_notice_plans_updated_by_admin_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notice_plans"),
    )
    op.create_index(
        "uq_notice_plans_slug_active",
        "notice_plans",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_notice_plans_published",
        "notice_plans",
        ["is_published", "updated_at"],
    )
    op.create_index(
        "ix_notice_plans_category",
        "notice_plans",
        ["category", "updated_at"],
    )
    op.create_index(
        "ix_notice_plans_created_by_admin",
        "notice_plans",
        ["created_by_admin_id"],
    )
    op.create_index(
        "ix_notice_plans_updated_by_admin",
        "notice_plans",
        ["updated_by_admin_id"],
    )

    op.create_table(
        "notice_pois",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.String(length=80, collation="C"), nullable=False),
        sa.Column("feature_id", sa.String(length=120)),
        sa.Column("map_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("memo", sa.Text()),
        sa.Column("budget", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KRW"),
        sa.Column("user_url", sa.Text()),
        sa.Column("custom_marker_color", sa.String(length=16)),
        sa.Column("custom_marker_icon", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("day_index >= 1", name="ck_notice_pois_day_index"),
        sa.CheckConstraint("version >= 1", name="ck_notice_pois_version"),
        sa.ForeignKeyConstraint(
            ["map_feature_id"],
            ["map_features.id"],
            name="fk_notice_pois_map_feature_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["notice_plan_id"],
            ["notice_plans.id"],
            name="fk_notice_pois_notice_plan_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notice_pois"),
    )
    op.create_index(
        "ix_notice_pois_plan_sort",
        "notice_pois",
        ["notice_plan_id", "day_index", "sort_order"],
    )
    op.create_index("ix_notice_pois_feature", "notice_pois", ["feature_id"])
    op.create_index("ix_notice_pois_map_feature", "notice_pois", ["map_feature_id"])


def downgrade() -> None:
    op.drop_index("ix_notice_pois_map_feature", table_name="notice_pois")
    op.drop_index("ix_notice_pois_feature", table_name="notice_pois")
    op.drop_index("ix_notice_pois_plan_sort", table_name="notice_pois")
    op.drop_table("notice_pois")
    op.drop_index("ix_notice_plans_updated_by_admin", table_name="notice_plans")
    op.drop_index("ix_notice_plans_created_by_admin", table_name="notice_plans")
    op.drop_index("ix_notice_plans_category", table_name="notice_plans")
    op.drop_index("ix_notice_plans_published", table_name="notice_plans")
    op.drop_index("uq_notice_plans_slug_active", table_name="notice_plans")
    op.drop_table("notice_plans")

    _drop_trip_date_range_constraint()
    op.alter_column("trip_days", "date", existing_type=sa.Date(), nullable=False)
    op.alter_column("trips", "end_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("trips", "start_date", existing_type=sa.Date(), nullable=False)
    op.create_check_constraint(
        op.f("ck_trips_date_range_order"),
        "trips",
        "end_date >= start_date",
    )


def _drop_trip_date_range_constraint() -> None:
    for name in (
        "ck_trips_date_range_order",
        "date_range_order",
        "ck_trips_ck_trips_date_range_order",
    ):
        op.execute(f'ALTER TABLE trips DROP CONSTRAINT IF EXISTS "{name}"')
