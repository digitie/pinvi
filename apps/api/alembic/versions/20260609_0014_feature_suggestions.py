"""feature suggestions queue

Revision ID: 20260609_0014
Revises: 20260608_0013
Create Date: 2026-06-09 11:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260609_0014"
down_revision: str | None = "20260608_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_suggestions",
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="new_place"),
        sa.Column("target_feature_id", sa.Text()),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("lat", sa.Numeric(8, 6), nullable=False),
        sa.Column(
            "categories",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("note", sa.Text()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_admin_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kor_travel_map_ref", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("request_id", name="pk_feature_suggestions"),
        sa.ForeignKeyConstraint(
            ["requester_user_id"],
            ["app.users.user_id"],
            name="fk_feature_suggestions_requester_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_admin_id"],
            ["app.users.user_id"],
            name="fk_feature_suggestions_reviewed_by_admin_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "type IN ('new_place', 'correction', 'closure')",
            name="ck_feature_suggestions_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'added', 'duplicate')",
            name="ck_feature_suggestions_status",
        ),
        sa.CheckConstraint(
            "kind IN ('place', 'event', 'notice', 'price', 'weather', 'route', 'area')",
            name="ck_feature_suggestions_kind",
        ),
        sa.CheckConstraint(
            "lng >= 124.0 AND lng <= 132.0 AND lat >= 33.0 AND lat <= 43.0",
            name="ck_feature_suggestions_korea_coord",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="ck_feature_suggestions_name",
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 2000",
            name="ck_feature_suggestions_note",
        ),
        schema="app",
    )
    op.create_index(
        "ix_feature_suggestions_requester_created_at",
        "feature_suggestions",
        ["requester_user_id", "created_at"],
        schema="app",
    )
    op.create_index(
        "ix_feature_suggestions_status_created_at",
        "feature_suggestions",
        ["status", "created_at"],
        schema="app",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_feature_suggestions_user_pending_dedup
        ON app.feature_suggestions (requester_user_id, kind, lower(name), lng, lat)
        WHERE status = 'pending'
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_feature_suggestions_touch_updated_at
        BEFORE UPDATE ON app.feature_suggestions
        FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_feature_suggestions_touch_updated_at ON app.feature_suggestions"
    )
    op.execute("DROP INDEX IF EXISTS app.ux_feature_suggestions_user_pending_dedup")
    op.drop_index(
        "ix_feature_suggestions_status_created_at",
        table_name="feature_suggestions",
        schema="app",
    )
    op.drop_index(
        "ix_feature_suggestions_requester_created_at",
        table_name="feature_suggestions",
        schema="app",
    )
    op.drop_table("feature_suggestions", schema="app")
