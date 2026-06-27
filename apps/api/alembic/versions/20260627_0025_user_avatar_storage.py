"""user avatar RustFS storage

Revision ID: 20260627_0025
Revises: 20260616_0024
Create Date: 2026-06-27 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260627_0025"
down_revision: str | None = "20260616_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_bucket", sa.String(length=80), nullable=True),
        schema="app",
    )
    op.add_column(
        "users",
        sa.Column("avatar_storage_key", sa.String(length=1024), nullable=True),
        schema="app",
    )
    op.add_column(
        "users",
        sa.Column("avatar_content_type", sa.String(length=255), nullable=True),
        schema="app",
    )
    op.add_column(
        "users",
        sa.Column("avatar_byte_size", sa.BigInteger(), nullable=True),
        schema="app",
    )
    op.add_column(
        "users",
        sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.create_table(
        "storage_settings",
        sa.Column("settings_id", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "avatar_max_upload_bytes",
            sa.BigInteger(),
            server_default=sa.text("2097152"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "settings_id = 1", name="ck_storage_settings_storage_settings_singleton"
        ),
        sa.CheckConstraint(
            "avatar_max_upload_bytes > 0",
            name="ck_storage_settings_storage_settings_avatar_max_upload_bytes_positive",
        ),
        sa.PrimaryKeyConstraint("settings_id", name="pk_storage_settings"),
        schema="app",
    )
    op.execute(
        sa.text(
            "INSERT INTO app.storage_settings (settings_id, avatar_max_upload_bytes) "
            "VALUES (1, 2097152)"
        )
    )


def downgrade() -> None:
    op.drop_table("storage_settings", schema="app")
    op.drop_column("users", "avatar_updated_at", schema="app")
    op.drop_column("users", "avatar_byte_size", schema="app")
    op.drop_column("users", "avatar_content_type", schema="app")
    op.drop_column("users", "avatar_storage_key", schema="app")
    op.drop_column("users", "avatar_bucket", schema="app")
