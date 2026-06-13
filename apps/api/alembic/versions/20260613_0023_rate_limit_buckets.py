"""rate limit buckets

Revision ID: 20260613_0023
Revises: 20260612_0022
Create Date: 2026-06-13 00:00:00

ADR-038: production/staging HTTP rate limiting uses app-owned PostgreSQL
fixed-window buckets so Uvicorn workers and deployment nodes share counters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0023"
down_revision: str | None = "20260612_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("bucket_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_name", sa.String(length=80), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_buckets_count_nonnegative"),
        sa.PrimaryKeyConstraint("bucket_hash", "window_start", name="pk_rate_limit_buckets"),
        schema="app",
    )
    op.create_index(
        "ix_rate_limit_buckets_expires_at",
        "rate_limit_buckets",
        ["expires_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_buckets_expires_at", table_name="rate_limit_buckets", schema="app")
    op.drop_table("rate_limit_buckets", schema="app")
