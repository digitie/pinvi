"""trip day marker_color + de-materialize auto dates (ADR-055)

Revision ID: 20260720_0038
Revises: 20260629_0037
Create Date: 2026-07-20 21:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260720_0038"
down_revision: str | None = "20260629_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR-055: 일자 마커 색 override(팔레트 키). NULL = 인덱스 기본색으로 파생.
    op.add_column(
        "trip_days",
        sa.Column("marker_color", sa.String(length=16), nullable=True),
        schema="app",
    )
    # ADR-055: date는 override-only가 된다. 과거 auto-materialize된 date(= start_date+(day_index-1)와
    # 정확히 일치)를 NULL로 되돌려 effective_date가 파생되게 한다. 파생값과 다른 override와
    # start_date 없는 여행의 date는 그대로 둔다.
    # 주의: 사용자가 파생값과 '동일한' 날짜를 우연히 override로 고정한 경우는 데이터만으로
    # 구분할 수 없어 auto-derived로 간주해 NULL 처리한다(이후 start_date 변경 시 함께 이동).
    op.execute(
        """
        UPDATE app.trip_days d
        SET date = NULL
        FROM app.trips t
        WHERE d.trip_id = t.trip_id
          AND t.start_date IS NOT NULL
          AND d.date IS NOT NULL
          AND d.date = t.start_date + (d.day_index - 1)
        """
    )


def downgrade() -> None:
    # NULL이 된 파생-date를 다시 materialize(가역성 확보). override/무-기간 여행은 영향 없음.
    op.execute(
        """
        UPDATE app.trip_days d
        SET date = t.start_date + (d.day_index - 1)
        FROM app.trips t
        WHERE d.trip_id = t.trip_id
          AND t.start_date IS NOT NULL
          AND d.date IS NULL
        """
    )
    op.drop_column("trip_days", "marker_color", schema="app")
