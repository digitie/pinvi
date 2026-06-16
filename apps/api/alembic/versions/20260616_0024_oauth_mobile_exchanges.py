"""oauth mobile exchange codes

Revision ID: 20260616_0024
Revises: 20260613_0023
Create Date: 2026-06-16 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260616_0024"
down_revision: str | None = "20260613_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_mobile_exchanges",
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("code_hash", name="pk_oauth_mobile_exchanges"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_oauth_mobile_exchanges_user_id",
            ondelete="CASCADE",
        ),
        schema="app",
    )
    op.create_index(
        "ix_oauth_mobile_exchanges_expires_at",
        "oauth_mobile_exchanges",
        ["expires_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_mobile_exchanges_expires_at",
        table_name="oauth_mobile_exchanges",
        schema="app",
    )
    op.drop_table("oauth_mobile_exchanges", schema="app")
