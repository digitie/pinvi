"""trip_days + trip_day_pois with sort_order TEXT COLLATE "C" (SPEC V8 E-6 Critical)

Revision ID: 20260602_0002
Revises: 20260602_0001
Create Date: 2026-06-02 10:00:00

`docs/postgres-schema.md` §3.3 / `docs/api/pois.md` / `docs/data-model.md` §2.3.

Critical: LexoRank 정합성 위해 sort_order는 TEXT COLLATE "C". JS ASCII와
PG 정렬 결과 일치 강제. en_US.utf8 콜레이션 사용 시 시스템 마비 위험.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0002"
down_revision: str | None = "20260602_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # trip_days — composite PK (trip_id, day_index)
    # ─────────────────────────────────────────────
    op.create_table(
        "trip_days",
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date()),
        sa.Column("title", sa.String(length=200)),
        sa.Column("note", sa.Text()),
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
        sa.PrimaryKeyConstraint("trip_id", "day_index", name="pk_trip_days"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_days_trip_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("day_index >= 1", name="ck_trip_days_day_index"),
        schema="app",
    )

    # ─────────────────────────────────────────────
    # trip_day_pois — sort_order TEXT COLLATE "C" + version optimistic lock
    # ─────────────────────────────────────────────
    op.create_table(
        "trip_day_pois",
        sa.Column(
            "attachment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column(
            "sort_order",
            sa.Text(collation="C"),
            nullable=False,
        ),
        sa.Column("feature_id", sa.Text(), nullable=False),
        sa.Column("feature_link_broken_at", sa.DateTime(timezone=True)),
        sa.Column(
            "feature_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("custom_marker_color", sa.String(length=16)),
        sa.Column("custom_marker_icon", sa.String(length=64)),
        sa.Column("planned_arrival_at", sa.DateTime(timezone=True)),
        sa.Column("planned_departure_at", sa.DateTime(timezone=True)),
        sa.Column("user_note", sa.Text()),
        sa.Column("budget_amount", sa.Numeric(12, 2)),
        sa.Column("actual_amount", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KRW"),
        sa.Column("user_url", sa.Text()),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("attachment_id", name="pk_trip_day_pois"),
        sa.ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["app.trip_days.trip_id", "app.trip_days.day_index"],
            name="fk_trip_day_pois_day",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["app.users.user_id"],
            name="fk_trip_day_pois_added_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "custom_marker_color IS NULL OR custom_marker_color SIMILAR TO 'P-[0-9]{2}'",
            name="ck_trip_day_pois_custom_marker_color",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_day_pois_feature",
        "trip_day_pois",
        ["feature_id"],
        schema="app",
    )
    op.create_index(
        "ix_trip_day_pois_trip_day",
        "trip_day_pois",
        ["trip_id", "day_index"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # sort_order UNIQUE — COLLATE "C" 명시. JS LexoRank와 정렬 일관
    op.execute(
        "CREATE UNIQUE INDEX uq_trip_day_pois_day_sort "
        'ON app.trip_day_pois (trip_id, day_index, sort_order COLLATE "C") '
        "WHERE deleted_at IS NULL"
    )

    op.execute(
        "CREATE TRIGGER trg_trip_day_pois_touch_updated_at "
        "BEFORE UPDATE ON app.trip_day_pois FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_trip_day_pois_touch_updated_at ON app.trip_day_pois")
    op.execute("DROP INDEX IF EXISTS app.uq_trip_day_pois_day_sort")
    op.drop_index("ix_trip_day_pois_trip_day", table_name="trip_day_pois", schema="app")
    op.drop_index("ix_trip_day_pois_feature", table_name="trip_day_pois", schema="app")
    op.drop_table("trip_day_pois", schema="app")
    op.drop_table("trip_days", schema="app")
