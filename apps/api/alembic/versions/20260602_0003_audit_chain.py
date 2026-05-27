"""location_access_log + admin_audit_log with content_hash chain

Revision ID: 20260602_0003
Revises: 20260602_0002
Create Date: 2026-06-02 11:00:00

`docs/compliance/lbs-act.md` §3 / `docs/data-model.md` §8.2 / `docs/spec/v8/00-infrastructure.md` §3.3.

Chain 검증: 직전 row의 content_hash + 현재 row 표준 표현 SHA-256.
중간 row 삭제 / 변조 시 chain 검증 가능 (append-only 사실상 강제).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0003"
down_revision: str | None = "20260602_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # location_access_log — 위치정보법 제16조 (6개월 보존)
    # ─────────────────────────────────────────────
    op.create_table(
        "location_access_log",
        sa.Column("log_id", sa.BigInteger(), primary_key=False, autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("log_id", name="pk_location_access_log"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_location_access_log_user_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "purpose IN ("
            "'viewport_query', 'nearby_attractions', 'weather_at_coord', "
            "'feature_request', 'region_covering', 'region_radius'"
            ")",
            name="ck_location_access_log_purpose",
        ),
        schema="app",
    )
    op.execute(
        "CREATE INDEX ix_location_access_log_occurred "
        "ON app.location_access_log USING brin (occurred_at)"
    )
    op.create_index(
        "ix_location_access_log_user_time",
        "location_access_log",
        ["user_id", sa.text("occurred_at DESC")],
        schema="app",
    )

    # ─────────────────────────────────────────────
    # admin_audit_log — SPEC V8 O-6 / M-14
    # ─────────────────────────────────────────────
    op.create_table(
        "admin_audit_log",
        sa.Column("log_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128)),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("access_reason", sa.Text()),
        sa.Column(
            "target_pii_fields",
            postgresql.ARRAY(sa.String(length=64)),
        ),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512)),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("log_id", name="pk_admin_audit_log"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.user_id"],
            name="fk_admin_audit_log_actor_user_id",
            ondelete="RESTRICT",
        ),
        schema="app",
    )
    op.execute(
        "CREATE INDEX ix_admin_audit_log_occurred ON app.admin_audit_log USING brin (occurred_at)"
    )
    op.create_index(
        "ix_admin_audit_log_resource",
        "admin_audit_log",
        ["resource_type", "resource_id", sa.text("occurred_at DESC")],
        schema="app",
    )

    # append-only 강제 — UPDATE / DELETE 차단 trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.audit_log_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit log is append-only — % blocked', TG_OP;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_location_access_log_append_only "
        "BEFORE UPDATE OR DELETE ON app.location_access_log "
        "FOR EACH ROW EXECUTE FUNCTION app.audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_admin_audit_log_append_only "
        "BEFORE UPDATE OR DELETE ON app.admin_audit_log "
        "FOR EACH ROW EXECUTE FUNCTION app.audit_log_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_admin_audit_log_append_only ON app.admin_audit_log")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_location_access_log_append_only ON app.location_access_log"
    )
    op.execute("DROP FUNCTION IF EXISTS app.audit_log_append_only()")
    op.drop_index("ix_admin_audit_log_resource", table_name="admin_audit_log", schema="app")
    op.execute("DROP INDEX IF EXISTS app.ix_admin_audit_log_occurred")
    op.drop_table("admin_audit_log", schema="app")
    op.drop_index(
        "ix_location_access_log_user_time", table_name="location_access_log", schema="app"
    )
    op.execute("DROP INDEX IF EXISTS app.ix_location_access_log_occurred")
    op.drop_table("location_access_log", schema="app")
