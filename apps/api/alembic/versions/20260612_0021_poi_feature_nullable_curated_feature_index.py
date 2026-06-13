"""poi feature_id nullable + curated feature lookup index

Revision ID: 20260612_0021
Revises: 20260610_0020
Create Date: 2026-06-12 00:00:00

ADR-031 permits trip POIs without a kor_travel_map feature link. ADR-036 clarifies that
external integrations may still upsert feature-backed curated POIs by feature_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260612_0021"
down_revision: str | None = "20260610_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "trip_day_pois",
        "feature_id",
        existing_type=sa.Text(),
        nullable=True,
        schema="app",
    )
    op.create_index(
        "ix_curated_plan_pois_feature",
        "curated_plan_pois",
        ["feature_id"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL AND feature_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_curated_plan_pois_feature", table_name="curated_plan_pois", schema="app")
    op.alter_column(
        "trip_day_pois",
        "feature_id",
        existing_type=sa.Text(),
        nullable=False,
        schema="app",
    )
