"""notice_plans + notice_pois + plan_poi_attachments

Revision ID: 20260602_0005
Revises: 20260602_0004
Create Date: 2026-06-02 13:00:00

`docs/architecture/notice-plans.md` §3 / `docs/api/notice-plans.md` / ADR-013.
주의: notice_plans (Pinvi 추천 여행) ≠ notice feature (라이브러리 공지/자연현상).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0005"
down_revision: str | None = "20260602_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # notice_plans
    # ─────────────────────────────────────────────
    op.create_table(
        "notice_plans",
        sa.Column(
            "notice_plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="recommended"),
        sa.Column("summary", sa.Text()),
        sa.Column("source_name", sa.String(length=200)),
        sa.Column("destination", sa.String(length=120)),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("notice_plan_id", name="pk_notice_plans"),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["app.users.user_id"],
            name="fk_notice_plans_created_by_admin_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["app.users.user_id"],
            name="fk_notice_plans_updated_by_admin_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(starts_on IS NULL AND ends_on IS NULL) OR "
            "(starts_on IS NOT NULL AND ends_on IS NOT NULL AND ends_on >= starts_on)",
            name="ck_notice_plans_date_range",
        ),
        schema="app",
    )
    op.create_index(
        "uq_notice_plans_slug_active",
        "notice_plans",
        ["slug"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_notice_plans_published",
        "notice_plans",
        ["is_published", sa.text("updated_at DESC")],
        schema="app",
    )
    op.create_index(
        "ix_notice_plans_category",
        "notice_plans",
        ["category", sa.text("updated_at DESC")],
        schema="app",
    )
    op.execute(
        "CREATE TRIGGER trg_notice_plans_touch_updated_at "
        "BEFORE UPDATE ON app.notice_plans FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    # ─────────────────────────────────────────────
    # notice_pois — sort_order TEXT COLLATE "C" (LexoRank)
    # ─────────────────────────────────────────────
    op.create_table(
        "notice_pois",
        sa.Column(
            "notice_poi_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("notice_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Text(collation="C"), nullable=False),
        sa.Column("feature_id", sa.Text()),
        sa.Column(
            "feature_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("memo", sa.Text()),
        sa.Column("budget_amount", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KRW"),
        sa.Column("user_url", sa.Text()),
        sa.Column("custom_marker_color", sa.String(length=16)),
        sa.Column("custom_marker_icon", sa.String(length=64)),
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
        sa.PrimaryKeyConstraint("notice_poi_id", name="pk_notice_pois"),
        sa.ForeignKeyConstraint(
            ["notice_plan_id"],
            ["app.notice_plans.notice_plan_id"],
            name="fk_notice_pois_notice_plan_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("day_index >= 1", name="ck_notice_pois_day_index"),
        sa.CheckConstraint(
            "custom_marker_color IS NULL OR custom_marker_color SIMILAR TO 'P-[0-9]{2}'",
            name="ck_notice_pois_custom_marker_color",
        ),
        schema="app",
    )
    op.create_index(
        "ix_notice_pois_plan_day",
        "notice_pois",
        ["notice_plan_id", "day_index"],
        schema="app",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_notice_pois_plan_day_sort "
        'ON app.notice_pois (notice_plan_id, day_index, sort_order COLLATE "C") '
        "WHERE deleted_at IS NULL"
    )

    # ─────────────────────────────────────────────
    # plan_poi_attachments — 단일 테이블 4 대상 (trip / trip_poi / notice_plan / notice_poi)
    # ─────────────────────────────────────────────
    op.create_table(
        "plan_poi_attachments",
        sa.Column(
            "attachment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True)),
        sa.Column("trip_poi_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notice_plan_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notice_poi_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("bucket", sa.String(length=80), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("public_url", sa.Text()),
        sa.Column("checksum_sha256", sa.String(length=64)),
        sa.Column(
            "role",
            sa.String(length=40),
            nullable=False,
            server_default="attachment",
        ),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("attachment_id", name="pk_plan_poi_attachments"),
        sa.CheckConstraint(
            "num_nonnulls(trip_id, trip_poi_id, notice_plan_id, notice_poi_id) = 1",
            name="ck_plan_poi_attachments_single_target",
        ),
        sa.CheckConstraint(
            "role IN ('attachment', 'image', 'document', 'reference')",
            name="ck_plan_poi_attachments_role",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_plan_poi_attachments_byte_size"),
        sa.CheckConstraint("sort_order >= 0", name="ck_plan_poi_attachments_sort_order"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_plan_poi_attachments_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_poi_id"],
            ["app.trip_day_pois.attachment_id"],
            name="fk_plan_poi_attachments_trip_poi_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notice_plan_id"],
            ["app.notice_plans.notice_plan_id"],
            name="fk_plan_poi_attachments_notice_plan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notice_poi_id"],
            ["app.notice_pois.notice_poi_id"],
            name="fk_plan_poi_attachments_notice_poi_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["app.plan_poi_attachments.attachment_id"],
            name="fk_plan_poi_attachments_source_attachment_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["app.users.user_id"],
            name="fk_plan_poi_attachments_uploaded_by_user_id",
            ondelete="RESTRICT",
        ),
        schema="app",
    )
    op.create_index(
        "ix_plan_poi_attachments_trip",
        "plan_poi_attachments",
        ["trip_id", "sort_order"],
        schema="app",
        postgresql_where=sa.text("trip_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_plan_poi_attachments_trip_poi",
        "plan_poi_attachments",
        ["trip_poi_id", "sort_order"],
        schema="app",
        postgresql_where=sa.text("trip_poi_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_plan_poi_attachments_notice_plan",
        "plan_poi_attachments",
        ["notice_plan_id", "sort_order"],
        schema="app",
        postgresql_where=sa.text("notice_plan_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_plan_poi_attachments_notice_poi",
        "plan_poi_attachments",
        ["notice_poi_id", "sort_order"],
        schema="app",
        postgresql_where=sa.text("notice_poi_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_plan_poi_attachments_storage_key",
        "plan_poi_attachments",
        ["bucket", "storage_key"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("plan_poi_attachments", schema="app")
    op.execute("DROP INDEX IF EXISTS app.uq_notice_pois_plan_day_sort")
    op.drop_index("ix_notice_pois_plan_day", table_name="notice_pois", schema="app")
    op.drop_table("notice_pois", schema="app")
    op.execute("DROP TRIGGER IF EXISTS trg_notice_plans_touch_updated_at ON app.notice_plans")
    op.drop_index("ix_notice_plans_category", table_name="notice_plans", schema="app")
    op.drop_index("ix_notice_plans_published", table_name="notice_plans", schema="app")
    op.drop_index("uq_notice_plans_slug_active", table_name="notice_plans", schema="app")
    op.drop_table("notice_plans", schema="app")
