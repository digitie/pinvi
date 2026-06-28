"""rate limit abuse overrides

Revision ID: 20260629_0034
Revises: 20260629_0033
Create Date: 2026-06-29 00:34:00

T-282: expose ADR-038 bucket state and TTL block/allow overrides for Admin abuse ops.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260629_0034"
down_revision: str | None = "20260629_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_rate_limit_buckets_limit_updated",
        "rate_limit_buckets",
        ["limit_name", "updated_at"],
        schema="app",
    )
    op.create_table(
        "rate_limit_overrides",
        sa.Column(
            "override_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("limit_name", sa.String(length=80), nullable=False),
        sa.Column("bucket_hash", sa.String(length=64), nullable=False),
        sa.Column("identity_kind", sa.String(length=32), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("identity_label", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "identity_kind IN ('ip', 'ip_email', 'user', 'shared_token')",
            name="ck_rate_limit_overrides_identity_kind_allowed",
        ),
        sa.CheckConstraint(
            "action IN ('blocked', 'allowed')",
            name="ck_rate_limit_overrides_action_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app.users.user_id"],
            name="fk_rate_limit_overrides_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["app.users.user_id"],
            name="fk_rate_limit_overrides_revoked_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("override_id", name="pk_rate_limit_overrides"),
        schema="app",
    )
    op.create_index(
        "ix_rate_limit_overrides_bucket_active",
        "rate_limit_overrides",
        ["bucket_hash", "limit_name", "expires_at"],
        schema="app",
    )
    op.create_index(
        "ix_rate_limit_overrides_created_at",
        "rate_limit_overrides",
        ["created_at"],
        schema="app",
    )
    op.create_index(
        "ix_rate_limit_overrides_expires_at",
        "rate_limit_overrides",
        ["expires_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_overrides_expires_at",
        table_name="rate_limit_overrides",
        schema="app",
    )
    op.drop_index(
        "ix_rate_limit_overrides_created_at",
        table_name="rate_limit_overrides",
        schema="app",
    )
    op.drop_index(
        "ix_rate_limit_overrides_bucket_active",
        table_name="rate_limit_overrides",
        schema="app",
    )
    op.drop_table("rate_limit_overrides", schema="app")
    op.drop_index(
        "ix_rate_limit_buckets_limit_updated",
        table_name="rate_limit_buckets",
        schema="app",
    )
