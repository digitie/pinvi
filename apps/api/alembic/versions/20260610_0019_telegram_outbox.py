"""telegram notification outbox

Revision ID: 20260610_0019
Revises: 20260610_0018
Create Date: 2026-06-10 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260610_0019"
down_revision: str | None = "20260610_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_system_notification_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_system_notification_outbox"),
        schema="app",
    )
    op.execute(
        """
        CREATE INDEX ix_telegram_outbox_pending
        ON app.telegram_system_notification_outbox (scheduled_at)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.ix_telegram_outbox_pending")
    op.drop_table("telegram_system_notification_outbox", schema="app")
