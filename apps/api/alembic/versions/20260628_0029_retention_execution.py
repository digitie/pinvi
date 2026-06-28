"""retention execution runs and location archive

Revision ID: 20260628_0029
Revises: 20260628_0028
Create Date: 2026-06-28 17:20:00

T-276: 실행 가능한 retention batch, evidence snapshot, location access log archive table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0029"
down_revision: str | None = "20260628_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_email_status", "users", schema="app", type_="check")
    op.create_check_constraint(
        "ck_users_email_status",
        "users",
        "email_status IN ('active', 'bounced', 'complained', 'suppressed')",
        schema="app",
    )

    op.create_table(
        "retention_runs",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="all"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "candidate_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "kill_switch_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("confirm_phrase", sa.Text(), nullable=True),
        sa.Column("access_reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("mode IN ('dry_run', 'execute')", name="ck_retention_runs_mode"),
        sa.CheckConstraint("scope IN ('all', 'pii', 'location')", name="ck_retention_runs_scope"),
        sa.CheckConstraint(
            "status IN ('dry_run', 'approved', 'executing', 'completed', 'failed', 'rolled_back')",
            name="ck_retention_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.user_id"],
            name="fk_retention_runs_actor_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_retention_runs"),
        schema="app",
    )
    op.create_index(
        "ix_retention_runs_created_at",
        "retention_runs",
        [sa.text("created_at DESC")],
        schema="app",
    )
    op.create_index(
        "ix_retention_runs_status",
        "retention_runs",
        ["status", sa.text("created_at DESC")],
        schema="app",
    )
    op.execute(
        "CREATE TRIGGER trg_retention_runs_touch_updated_at "
        "BEFORE UPDATE ON app.retention_runs "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    op.create_table(
        "location_access_log_archive",
        sa.Column("log_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("retention_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["retention_run_id"],
            ["app.retention_runs.run_id"],
            name="fk_location_access_log_archive_retention_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_location_access_log_archive_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("log_id", name="pk_location_access_log_archive"),
        schema="app",
    )
    op.execute(
        "CREATE INDEX ix_location_access_log_archive_occurred "
        "ON app.location_access_log_archive USING brin (occurred_at)"
    )
    op.create_index(
        "ix_location_access_log_archive_run",
        "location_access_log_archive",
        ["retention_run_id", sa.text("log_id DESC")],
        schema="app",
    )
    op.create_index(
        "ix_location_access_log_archive_user_time",
        "location_access_log_archive",
        ["user_id", sa.text("occurred_at DESC")],
        schema="app",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.audit_log_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_TABLE_SCHEMA = 'app'
             AND TG_TABLE_NAME = 'location_access_log'
             AND TG_OP = 'DELETE'
             AND current_setting('app.retention_location_delete_allowed', true) = 'on' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'audit log is append-only — % blocked', TG_OP;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("UPDATE app.users SET email_status = 'active' WHERE email_status = 'suppressed'")
    op.drop_constraint("ck_users_email_status", "users", schema="app", type_="check")
    op.create_check_constraint(
        "ck_users_email_status",
        "users",
        "email_status IN ('active', 'bounced', 'complained')",
        schema="app",
    )
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
    op.drop_index(
        "ix_location_access_log_archive_user_time",
        table_name="location_access_log_archive",
        schema="app",
    )
    op.drop_index(
        "ix_location_access_log_archive_run",
        table_name="location_access_log_archive",
        schema="app",
    )
    op.execute("DROP INDEX IF EXISTS app.ix_location_access_log_archive_occurred")
    op.drop_table("location_access_log_archive", schema="app")
    op.execute("DROP TRIGGER IF EXISTS trg_retention_runs_touch_updated_at ON app.retention_runs")
    op.drop_index("ix_retention_runs_status", table_name="retention_runs", schema="app")
    op.drop_index("ix_retention_runs_created_at", table_name="retention_runs", schema="app")
    op.drop_table("retention_runs", schema="app")
