"""mcp token table

Revision ID: 20260609_0016
Revises: 20260609_0015
Create Date: 2026-06-09 13:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260609_0016"
down_revision: str | None = "20260609_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_tokens",
        sa.Column(
            "token_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_suffix", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default=sa.text("ARRAY['mcp:read']::varchar[]"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_ip_hash", sa.String(length=64)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("token_id", name="pk_mcp_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_mcp_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_mcp_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120",
            name="ck_mcp_tokens_mcp_tokens_name_length",
        ),
        sa.CheckConstraint(
            "cardinality(scopes) > 0 AND scopes <@ ARRAY['mcp:read']::varchar[]",
            name="ck_mcp_tokens_mcp_tokens_scopes_allowed",
        ),
        schema="app",
    )
    op.create_index(
        "ix_mcp_tokens_user_created_at",
        "mcp_tokens",
        ["user_id", "created_at"],
        schema="app",
    )
    op.create_index(
        "ix_mcp_tokens_expires_at",
        "mcp_tokens",
        ["expires_at"],
        schema="app",
    )
    op.execute(
        """
        CREATE INDEX ix_mcp_tokens_user_active
        ON app.mcp_tokens (user_id, updated_at DESC)
        WHERE revoked_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_mcp_tokens_touch_updated_at
        BEFORE UPDATE ON app.mcp_tokens
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mcp_tokens_touch_updated_at ON app.mcp_tokens")
    op.execute("DROP INDEX IF EXISTS app.ix_mcp_tokens_user_active")
    op.drop_index("ix_mcp_tokens_expires_at", table_name="mcp_tokens", schema="app")
    op.drop_index("ix_mcp_tokens_user_created_at", table_name="mcp_tokens", schema="app")
    op.drop_table("mcp_tokens", schema="app")
