"""trips + trip_companions + trip_share_links

Revision ID: 20260602_0001
Revises: 20260601_0001
Create Date: 2026-06-02 09:00:00

`docs/data-model.md` §2.2 / `docs/postgres-schema.md` §3.1 / `docs/api/trips.md`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0001"
down_revision: str | None = "20260601_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # trips
    # ─────────────────────────────────────────────
    op.create_table(
        "trips",
        sa.Column(
            "trip_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("region_hint", sa.String(length=120)),
        sa.Column("cover_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("fuel_types", postgresql.ARRAY(sa.String(length=16))),
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="private",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint("trip_id", name="pk_trips"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app.users.user_id"],
            name="fk_trips_owner_user_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(start_date IS NULL AND end_date IS NULL) OR "
            "(start_date IS NOT NULL AND end_date IS NOT NULL AND end_date >= start_date)",
            name="ck_trips_date_range",
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name="ck_trips_visibility",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'planned', 'in_progress', 'completed', 'archived')",
            name="ck_trips_status",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trips_owner_status",
        "trips",
        ["owner_user_id", "status", "start_date"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_trips_touch_updated_at "
        "BEFORE UPDATE ON app.trips FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    # ─────────────────────────────────────────────
    # trip_companions (가입 전 invited_email + 가입 후 user_id)
    # ─────────────────────────────────────────────
    op.create_table(
        "trip_companions",
        sa.Column(
            "companion_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("invited_email", sa.String(length=320)),
        sa.Column("invited_nickname", sa.String(length=80)),
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            server_default="editor",
        ),
        sa.Column(
            "invited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("companion_id", name="pk_trip_companions"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_companions_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_trip_companions_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "(user_id IS NOT NULL) OR (invited_email IS NOT NULL)",
            name="ck_trip_companions_target",
        ),
        sa.CheckConstraint(
            "role IN ('co_owner', 'editor', 'viewer')",
            name="ck_trip_companions_role",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_companions_trip", "trip_companions", ["trip_id"], schema="app"
    )
    op.create_index(
        "ix_trip_companions_user",
        "trip_companions",
        ["user_id"],
        schema="app",
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_trip_companions_trip_user "
        "ON app.trip_companions (trip_id, user_id) WHERE user_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_trip_companions_trip_invited "
        "ON app.trip_companions (trip_id, lower(invited_email)) WHERE invited_email IS NOT NULL"
    )

    # ─────────────────────────────────────────────
    # trip_share_links (256bit URL-safe base64 token hash)
    # ─────────────────────────────────────────────
    op.create_table(
        "trip_share_links",
        sa.Column(
            "share_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="view_only",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("share_id", name="pk_trip_share_links"),
        sa.UniqueConstraint("token_hash", name="uq_trip_share_links_token_hash"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_share_links_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app.users.user_id"],
            name="fk_trip_share_links_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "visibility IN ('view_only', 'comment', 'edit')",
            name="ck_trip_share_links_visibility",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_share_links_trip_active",
        "trip_share_links",
        ["trip_id"],
        schema="app",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trip_share_links_trip_active",
        table_name="trip_share_links",
        schema="app",
    )
    op.drop_table("trip_share_links", schema="app")
    op.execute("DROP INDEX IF EXISTS app.uq_trip_companions_trip_invited")
    op.execute("DROP INDEX IF EXISTS app.uq_trip_companions_trip_user")
    op.drop_index("ix_trip_companions_user", table_name="trip_companions", schema="app")
    op.drop_index("ix_trip_companions_trip", table_name="trip_companions", schema="app")
    op.drop_table("trip_companions", schema="app")
    op.execute("DROP TRIGGER IF EXISTS trg_trips_touch_updated_at ON app.trips")
    op.drop_index("ix_trips_owner_status", table_name="trips", schema="app")
    op.drop_table("trips", schema="app")
