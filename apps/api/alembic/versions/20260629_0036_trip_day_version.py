"""trip day optimistic-lock version

Revision ID: 20260629_0036
Revises: 20260629_0035
Create Date: 2026-06-29 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260629_0036"
down_revision: str | None = "20260629_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 row는 server_default 1로 backfill 후 NOT NULL — trip/POI와 동일한 정수 version
    # optimistic lock(If-Match)을 day rename/delete에 도입한다 (T-287, ADR 패턴 일치).
    op.add_column(
        "trip_days",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("trip_days", "version", schema="app")
