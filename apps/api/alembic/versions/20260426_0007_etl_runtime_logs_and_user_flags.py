"""add etl runtime logs and user flags

Revision ID: 20260426_0007
Revises: 20260425_0006
Create Date: 2026-04-26 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260426_0007"
down_revision: str | None = "20260425_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("is_privileged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "is_admin", server_default=None)
    op.alter_column("users", "is_privileged", server_default=None)

    op.create_table(
        "etl_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("run_key", sa.String(length=80), nullable=True),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log_file_path", sa.String(length=500), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_etl_run_logs"),
    )
    op.create_index("ix_etl_run_logs_dataset_key", "etl_run_logs", ["dataset_key"])
    op.create_index(
        "ix_etl_run_logs_dataset_run_key",
        "etl_run_logs",
        ["dataset_key", "run_key"],
    )
    op.create_index("ix_etl_run_logs_status", "etl_run_logs", ["status"])

    op.create_table(
        "admin_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_scope", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=True),
        sa.Column("etl_run_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["etl_run_log_id"],
            ["etl_run_logs.id"],
            name="fk_admin_notifications_etl_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_notifications"),
    )
    op.create_index("ix_admin_notifications_dataset_key", "admin_notifications", ["dataset_key"])
    op.create_index("ix_admin_notifications_scope", "admin_notifications", ["recipient_scope"])
    op.create_index("ix_admin_notifications_unread", "admin_notifications", ["is_read"])

    op.create_table(
        "telegram_system_notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_scope", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=True),
        sa.Column("etl_run_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["etl_run_log_id"],
            ["etl_run_logs.id"],
            name="fk_tg_sys_outbox_etl_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tg_sys_outbox"),
    )
    op.create_index(
        "ix_tg_sys_outbox_dataset_key",
        "telegram_system_notification_outbox",
        ["dataset_key"],
    )
    op.create_index(
        "ix_tg_sys_outbox_status",
        "telegram_system_notification_outbox",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_tg_sys_outbox_status", table_name="telegram_system_notification_outbox")
    op.drop_index("ix_tg_sys_outbox_dataset_key", table_name="telegram_system_notification_outbox")
    op.drop_table("telegram_system_notification_outbox")

    op.drop_index("ix_admin_notifications_unread", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_scope", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_dataset_key", table_name="admin_notifications")
    op.drop_table("admin_notifications")

    op.drop_index("ix_etl_run_logs_status", table_name="etl_run_logs")
    op.drop_index("ix_etl_run_logs_dataset_run_key", table_name="etl_run_logs")
    op.drop_index("ix_etl_run_logs_dataset_key", table_name="etl_run_logs")
    op.drop_table("etl_run_logs")

    op.drop_column("users", "is_privileged")
    op.drop_column("users", "is_admin")
