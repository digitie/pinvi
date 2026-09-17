"""날씨 소스 이관(ADR-068) feature_id -> location_id 해석 캐시 테이블을 추가한다.

Revision ID: 20260917_0102
Revises: 20260824_0101
Create Date: 2026-09-17

T-361(P2). `kor-travel-weather`의 좌표 해석(`/v1/weather/resolve`)은 1회 호출에
3.1 MB급 응답이라 조회 경로에 둘 수 없다 — 결과를 `app.weather_location_links`에
캐시한다. `source_location_ids`를 배열로 통째 저장하는 이유는
`docs/integrations/kor-travel-weather.md` §3.3 참조(대표 location 하나만 캐시하면
기상청 예보가 조용히 누락된다).

이 테이블은 아직 어떤 라우터도 읽지 않는다 — T-362/T-363이 처음 읽는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260917_0102"
down_revision: str | None = "20260824_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_location_links",
        sa.Column("feature_id", sa.Text(), nullable=False),
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.Column("source_location_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column(
            "measurement_point",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stale", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_weather_location_links"),
        schema="app",
    )
    op.create_index(
        "ix_weather_location_links_stale",
        "weather_location_links",
        ["stale"],
        schema="app",
        postgresql_where=sa.text("stale"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_location_links_stale",
        table_name="weather_location_links",
        schema="app",
    )
    op.drop_table("weather_location_links", schema="app")
