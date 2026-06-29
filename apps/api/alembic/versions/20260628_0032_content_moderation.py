"""content moderation and takedown workflow

Revision ID: 20260628_0032
Revises: 20260628_0031
Create Date: 2026-06-28 23:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0032"
down_revision: str | None = "20260628_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_reports",
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_trip_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reporter_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column(
            "target_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resolution_summary", sa.Text()),
        sa.Column("appeal_summary", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("actioned_at", sa.DateTime(timezone=True)),
        sa.Column("appealed_at", sa.DateTime(timezone=True)),
        sa.Column("restored_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("report_id", name="pk_content_reports"),
        sa.ForeignKeyConstraint(
            ["target_trip_id"],
            ["app.trips.trip_id"],
            name="fk_content_reports_target_trip_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_owner_user_id"],
            ["app.users.user_id"],
            name="fk_content_reports_target_owner_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"],
            ["app.users.user_id"],
            name="fk_content_reports_reporter_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["app.users.user_id"],
            name="fk_content_reports_reviewer_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "target_type IN ('trip', 'comment', 'attachment', 'share_link')",
            name="ck_content_reports_target_type_allowed",
        ),
        sa.CheckConstraint(
            "reason_code IN ('spam', 'harassment', 'privacy', 'illegal', 'safety', 'other')",
            name="ck_content_reports_reason_code_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'reviewing', 'hidden', 'taken_down', "
            "'rejected', 'appealed', 'restored')",
            name="ck_content_reports_status_allowed",
        ),
        schema="app",
    )
    op.create_index(
        "ix_content_reports_status_created",
        "content_reports",
        ["status", sa.text("created_at DESC")],
        schema="app",
    )
    op.create_index(
        "ix_content_reports_target",
        "content_reports",
        ["target_type", "target_id"],
        schema="app",
    )
    op.create_index(
        "ix_content_reports_reporter_created",
        "content_reports",
        ["reporter_user_id", sa.text("created_at DESC")],
        schema="app",
        postgresql_where=sa.text("reporter_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_content_reports_owner_created",
        "content_reports",
        ["target_owner_user_id", sa.text("created_at DESC")],
        schema="app",
        postgresql_where=sa.text("target_owner_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_content_reports_trip_created",
        "content_reports",
        ["target_trip_id", sa.text("created_at DESC")],
        schema="app",
        postgresql_where=sa.text("target_trip_id IS NOT NULL"),
    )
    op.create_index(
        "ix_content_reports_open",
        "content_reports",
        ["created_at"],
        schema="app",
        postgresql_where=sa.text("status IN ('received', 'reviewing', 'appealed')"),
    )
    op.create_table(
        "content_moderation_actions",
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("action_reason", sa.Text(), nullable=False),
        sa.Column(
            "before_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "after_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("action_id", name="pk_content_moderation_actions"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["app.content_reports.report_id"],
            name="fk_content_moderation_actions_report_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.user_id"],
            name="fk_content_moderation_actions_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "action IN ('review', 'hide', 'takedown', 'restore', 'reject', 'appeal')",
            name="ck_content_moderation_actions_action_allowed",
        ),
        schema="app",
    )
    op.create_index(
        "ix_content_moderation_actions_report_created",
        "content_moderation_actions",
        ["report_id", sa.text("created_at DESC")],
        schema="app",
    )
    op.create_index(
        "ix_content_moderation_actions_actor_created",
        "content_moderation_actions",
        ["actor_user_id", sa.text("created_at DESC")],
        schema="app",
        postgresql_where=sa.text("actor_user_id IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_content_reports_touch_updated_at "
        "BEFORE UPDATE ON app.content_reports FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_content_reports_touch_updated_at ON app.content_reports")
    op.drop_index(
        "ix_content_moderation_actions_actor_created",
        table_name="content_moderation_actions",
        schema="app",
    )
    op.drop_index(
        "ix_content_moderation_actions_report_created",
        table_name="content_moderation_actions",
        schema="app",
    )
    op.drop_table("content_moderation_actions", schema="app")
    op.drop_index("ix_content_reports_open", table_name="content_reports", schema="app")
    op.drop_index("ix_content_reports_trip_created", table_name="content_reports", schema="app")
    op.drop_index("ix_content_reports_owner_created", table_name="content_reports", schema="app")
    op.drop_index("ix_content_reports_reporter_created", table_name="content_reports", schema="app")
    op.drop_index("ix_content_reports_target", table_name="content_reports", schema="app")
    op.drop_index("ix_content_reports_status_created", table_name="content_reports", schema="app")
    op.drop_table("content_reports", schema="app")
