"""category mapping overrides

Revision ID: 20260629_0035
Revises: 20260629_0034
Create Date: 2026-06-29 03:35:00

T-264: persist Pinvi-local Admin category mapping presentation overrides.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260629_0035"
down_revision: str | None = "20260629_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_mappings",
        sa.Column("category_key", sa.Text(), nullable=False),
        sa.Column("display_name_ko", sa.Text(), nullable=True),
        sa.Column("marker_color", sa.Text(), nullable=True),
        sa.Column("marker_icon", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "display_name_ko IS NULL OR length(btrim(display_name_ko)) BETWEEN 1 AND 120",
            name="ck_category_mappings_display_name",
        ),
        sa.CheckConstraint(
            "marker_color IS NULL OR marker_color ~ '^P-(0[1-9]|1[0-6])$'",
            name="ck_category_mappings_marker_color",
        ),
        sa.CheckConstraint(
            "marker_icon IS NULL OR marker_icon ~ '^[a-z0-9_-]{1,64}$'",
            name="ck_category_mappings_marker_icon",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app.users.user_id"],
            name="fk_category_mappings_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["app.users.user_id"],
            name="fk_category_mappings_updated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("category_key", name="pk_category_mappings"),
        schema="app",
    )
    op.create_index(
        "ix_category_mappings_updated_at",
        "category_mappings",
        ["updated_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_category_mappings_updated_at",
        table_name="category_mappings",
        schema="app",
    )
    op.drop_table("category_mappings", schema="app")
