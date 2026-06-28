"""email deliverability suppression and webhook ledger

Revision ID: 20260628_0030
Revises: 20260628_0029
Create Date: 2026-06-28 19:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0030"
down_revision: str | None = "20260628_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMAIL_QUEUE_STATUS_NEW = (
    "status IN ('pending', 'sent', 'delivered', 'delivery_delayed', "
    "'bounced', 'complained', 'suppressed', 'failed')"
)
EMAIL_QUEUE_STATUS_OLD = (
    "status IN ('pending', 'sent', 'delivered', 'bounced', 'complained', 'failed')"
)


def upgrade() -> None:
    op.drop_constraint("ck_email_queue_status", "email_queue", schema="app", type_="check")
    op.create_check_constraint(
        "ck_email_queue_status",
        "email_queue",
        EMAIL_QUEUE_STATUS_NEW,
        schema="app",
    )
    op.add_column(
        "email_queue",
        sa.Column("last_provider_event_id", sa.String(length=128)),
        schema="app",
    )
    op.add_column(
        "email_queue",
        sa.Column("last_provider_event_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.create_index(
        "ix_email_queue_provider_event",
        "email_queue",
        ["last_provider_event_id"],
        schema="app",
    )

    op.create_table(
        "email_suppressions",
        sa.Column(
            "suppression_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="resend"),
        sa.Column("provider_event_id", sa.String(length=128)),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("release_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("suppression_id", name="pk_email_suppressions"),
        sa.UniqueConstraint("email_hash", name="uq_email_suppressions_email_hash"),
        sa.ForeignKeyConstraint(
            ["released_by_user_id"],
            ["app.users.user_id"],
            name="fk_email_suppressions_released_by_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "reason IN ('hard_bounce', 'complaint', 'provider_suppressed', 'manual')",
            name="ck_email_suppressions_reason",
        ),
        sa.CheckConstraint("source IN ('resend', 'admin')", name="ck_email_suppressions_source"),
        schema="app",
    )
    op.create_index(
        "ix_email_suppressions_active_hash",
        "email_suppressions",
        ["email_hash"],
        schema="app",
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_email_suppressions_reason",
        "email_suppressions",
        ["reason"],
        schema="app",
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_email_suppressions_touch_updated_at "
        "BEFORE UPDATE ON app.email_suppressions FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    op.create_table(
        "resend_webhook_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("svix_id", sa.String(length=128)),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_ref", postgresql.UUID(as_uuid=True)),
        sa.Column("resend_email_id", sa.String(length=128)),
        sa.Column("event_created_at", sa.DateTime(timezone=True)),
        sa.Column(
            "payload_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_resend_webhook_events"),
        sa.UniqueConstraint("svix_id", name="uq_resend_webhook_events_svix_id"),
        schema="app",
    )
    op.create_index(
        "ix_resend_webhook_events_processed",
        "resend_webhook_events",
        ["processed_at"],
        schema="app",
    )
    op.create_index(
        "ix_resend_webhook_events_entity",
        "resend_webhook_events",
        ["entity_ref", "processed_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resend_webhook_events_entity", table_name="resend_webhook_events", schema="app"
    )
    op.drop_index(
        "ix_resend_webhook_events_processed", table_name="resend_webhook_events", schema="app"
    )
    op.drop_table("resend_webhook_events", schema="app")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_email_suppressions_touch_updated_at ON app.email_suppressions"
    )
    op.drop_index("ix_email_suppressions_reason", table_name="email_suppressions", schema="app")
    op.drop_index(
        "ix_email_suppressions_active_hash", table_name="email_suppressions", schema="app"
    )
    op.drop_table("email_suppressions", schema="app")

    op.drop_index("ix_email_queue_provider_event", table_name="email_queue", schema="app")
    op.drop_column("email_queue", "last_provider_event_at", schema="app")
    op.drop_column("email_queue", "last_provider_event_id", schema="app")
    op.execute(
        "UPDATE app.email_queue SET status = 'failed' WHERE status IN ('delivery_delayed', 'suppressed')"
    )
    op.drop_constraint("ck_email_queue_status", "email_queue", schema="app", type_="check")
    op.create_check_constraint(
        "ck_email_queue_status",
        "email_queue",
        EMAIL_QUEUE_STATUS_OLD,
        schema="app",
    )
