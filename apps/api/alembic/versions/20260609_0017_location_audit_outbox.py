"""location audit async outbox (T-146 / D-20)

요청 경로에서 체인 해시를 동기 계산하지 않도록(단일 노드 hotspot 제거), 좌표 접근 이벤트를
append-only outbox에 빠르게 적재하고 단일 writer worker가 `location_access_log` 체인으로 drain한다.

Revision ID: 20260609_0017
Revises: 20260609_0016
Create Date: 2026-06-09 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260609_0017"
down_revision: str | None = "20260609_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_audit_outbox",
        sa.Column("outbox_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("outbox_id", name="pk_location_audit_outbox"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_location_audit_outbox_user_id",
            ondelete="RESTRICT",
        ),
        schema="app",
    )
    # drain 큐 — 미처리(processed_at IS NULL) 행을 outbox_id 순서로 조회.
    op.create_index(
        "ix_location_audit_outbox_pending",
        "location_audit_outbox",
        ["outbox_id"],
        unique=False,
        schema="app",
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_location_audit_outbox_pending",
        table_name="location_audit_outbox",
        schema="app",
    )
    op.drop_table("location_audit_outbox", schema="app")
