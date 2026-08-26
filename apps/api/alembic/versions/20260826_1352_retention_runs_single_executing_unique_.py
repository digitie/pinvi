"""retention runs single executing unique index

Revision ID: 20260826_1352
Revises: 20260824_0101
Create Date: 2026-08-26 13:52:47.247060

`app.retention_runs`에 `status='executing'`이 최대 1개라는 불변식(T-343)은 지금
`_assert_no_concurrent_execution`의 advisory-lock 규율에만 의존한다(T-349). 유일한 호출
경로는 안전하지만 그 함수를 거치지 않는 다른 코드 경로나 수동 SQL을 막을 DB 차원 방어선이
없었다. 이 partial unique index는 defense-in-depth일 뿐 애플리케이션 락 규율을 대체하지
않는다 — 애플리케이션은 여전히 advisory lock으로 409를 먼저 반환하고, 이 제약은 그 규율이
깨졌을 때만(버그·수동 INSERT) 마지막 보루로 작동한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_1352"
down_revision: str | None = "20260824_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_retention_runs_single_executing",
        "retention_runs",
        ["status"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'executing'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_retention_runs_single_executing",
        table_name="retention_runs",
        schema="app",
    )
