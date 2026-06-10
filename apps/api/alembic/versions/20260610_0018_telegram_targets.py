"""telegram targets table

Revision ID: 20260610_0018
Revises: 20260609_0017
Create Date: 2026-06-10 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260610_0018"
down_revision: str | None = "20260609_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "telegram_bot_token_ref",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
        sa.Column("telegram_chat_type", sa.String(length=16)),
        sa.Column("telegram_message_thread_id", sa.String(length=64)),
        sa.Column("telegram_label", sa.String(length=80)),
        sa.Column("title_snapshot", sa.String(length=255)),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_send_status", sa.String(length=32)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_targets"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_telegram_targets_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(telegram_chat_id) BETWEEN 1 AND 64",
            name="ck_telegram_targets_telegram_targets_chat_id_length",
        ),
        schema="app",
    )
    op.execute(
        """
        CREATE INDEX ix_telegram_targets_user_active
        ON app.telegram_targets (user_id, created_at DESC)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_telegram_targets_touch_updated_at
        BEFORE UPDATE ON app.telegram_targets
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_telegram_targets_touch_updated_at ON app.telegram_targets"
    )
    op.execute("DROP INDEX IF EXISTS app.ix_telegram_targets_user_active")
    op.drop_table("telegram_targets", schema="app")
