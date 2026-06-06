"""trip comments

Revision ID: 20260606_0008
Revises: 20260606_0007
Create Date: 2026-06-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260606_0008"
down_revision: str | None = "20260606_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip_comments",
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "target_type",
            sa.String(length=16),
            nullable=False,
            server_default="trip",
        ),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("day_index", sa.Integer()),
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
        sa.PrimaryKeyConstraint("comment_id", name="pk_trip_comments"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_comments_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["app.users.user_id"],
            name="fk_trip_comments_author_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "target_type IN ('trip', 'day', 'poi')",
            name="ck_trip_comments_target_type",
        ),
        sa.CheckConstraint(
            "length(body) BETWEEN 1 AND 2000",
            name="ck_trip_comments_body_len",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_comments_trip_created_at",
        "trip_comments",
        ["trip_id", "created_at"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_trip_comments_author",
        "trip_comments",
        ["author_user_id"],
        schema="app",
        postgresql_where=sa.text("author_user_id IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_trip_comments_touch_updated_at "
        "BEFORE UPDATE ON app.trip_comments FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_trip_comments_touch_updated_at ON app.trip_comments")
    op.drop_index("ix_trip_comments_author", table_name="trip_comments", schema="app")
    op.drop_index("ix_trip_comments_trip_created_at", table_name="trip_comments", schema="app")
    op.drop_table("trip_comments", schema="app")
