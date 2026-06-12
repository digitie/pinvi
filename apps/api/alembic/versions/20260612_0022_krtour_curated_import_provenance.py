"""krtour curated import provenance

Revision ID: 20260612_0022
Revises: 20260612_0021
Create Date: 2026-06-12 00:00:00

T-223d: krtour-map curated feature copy snapshot을 TripMate curated plan으로
가져올 때 source version/etag와 item provenance를 저장한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260612_0022"
down_revision: str | None = "20260612_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("curated_trip_plans", sa.Column("source_system", sa.String(80)), schema="app")
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curated_feature_id", sa.Text()),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curated_feature_version", sa.Integer()),
        schema="app",
    )
    op.add_column("curated_trip_plans", sa.Column("source_etag", sa.String(128)), schema="app")
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_imported_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.create_index(
        "uq_curated_trip_plans_source_active",
        "curated_trip_plans",
        ["source_system", "source_curated_feature_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "deleted_at IS NULL "
            "AND source_system IS NOT NULL "
            "AND source_curated_feature_id IS NOT NULL"
        ),
    )

    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curated_feature_id", sa.Text()),
        schema="app",
    )
    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curated_feature_item_id", sa.Text()),
        schema="app",
    )
    op.create_index(
        "ix_curated_plan_pois_source_item",
        "curated_plan_pois",
        ["source_curated_feature_id", "source_curated_feature_item_id"],
        schema="app",
        postgresql_where=sa.text(
            "deleted_at IS NULL "
            "AND source_curated_feature_id IS NOT NULL "
            "AND source_curated_feature_item_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_curated_plan_pois_source_item", table_name="curated_plan_pois", schema="app")
    op.drop_column("curated_plan_pois", "source_curated_feature_item_id", schema="app")
    op.drop_column("curated_plan_pois", "source_curated_feature_id", schema="app")

    op.drop_index(
        "uq_curated_trip_plans_source_active", table_name="curated_trip_plans", schema="app"
    )
    op.drop_column("curated_trip_plans", "source_imported_at", schema="app")
    op.drop_column("curated_trip_plans", "source_etag", schema="app")
    op.drop_column("curated_trip_plans", "source_curated_feature_version", schema="app")
    op.drop_column("curated_trip_plans", "source_curated_feature_id", schema="app")
    op.drop_column("curated_trip_plans", "source_system", schema="app")
