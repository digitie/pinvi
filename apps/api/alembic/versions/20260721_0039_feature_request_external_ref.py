"""feature-request source/external_ref first-class + global dedup (ADR-054)

Revision ID: 20260721_0039
Revises: 20260720_0038
Create Date: 2026-07-21 08:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260721_0039"
down_revision: str | None = "20260720_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # POI/suggestion 출처(source) + 외부 opaque 참조(external_ref = {provider, external_id,
    # deep_link_url}). ADR-054 §7: 저장 대상은 user-authored 값 + external_ref뿐(provider 콘텐츠 미저장).
    op.add_column(
        "trip_day_pois",
        sa.Column("source", sa.String(length=16), nullable=True),
        schema="app",
    )
    op.add_column(
        "trip_day_pois",
        sa.Column("external_ref", JSONB(), nullable=True),
        schema="app",
    )
    op.add_column(
        "feature_suggestions",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="user"),
        schema="app",
    )
    op.add_column(
        "feature_suggestions",
        sa.Column("external_ref", JSONB(), nullable=True),
        schema="app",
    )

    # 재조정(reconciliation) 조회용 — 아직 feature에 연결되지 않은 외부-참조 POI를 (provider,
    # external_id)로 빠르게 찾는다.
    op.create_index(
        "ix_trip_day_pois_external_ref",
        "trip_day_pois",
        [sa.text("(external_ref->>'provider')"), sa.text("(external_ref->>'external_id')")],
        schema="app",
        postgresql_where=sa.text(
            "external_ref IS NOT NULL AND feature_id IS NULL AND deleted_at IS NULL"
        ),
    )
    # GLOBAL dedup — 같은 외부 장소(provider+external_id)에 대한 active 제안은 전역 1건만 허용한다
    # (ADR-054). rejected/duplicate는 index에서 빠져 재요청을 허용한다.
    op.create_index(
        "uq_feature_suggestions_active_external_ref",
        "feature_suggestions",
        [sa.text("(external_ref->>'provider')"), sa.text("(external_ref->>'external_id')")],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "external_ref IS NOT NULL AND status IN ('pending', 'approved', 'added')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_feature_suggestions_active_external_ref",
        table_name="feature_suggestions",
        schema="app",
    )
    op.drop_index("ix_trip_day_pois_external_ref", table_name="trip_day_pois", schema="app")
    op.drop_column("feature_suggestions", "external_ref", schema="app")
    op.drop_column("feature_suggestions", "source", schema="app")
    op.drop_column("trip_day_pois", "external_ref", schema="app")
    op.drop_column("trip_day_pois", "source", schema="app")
