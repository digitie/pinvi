"""data subject request intake workflow

Revision ID: 20260628_0031
Revises: 20260628_0030
Create Date: 2026-06-28 23:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0031"
down_revision: str | None = "20260628_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dsr_requests",
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("request_summary", sa.String(length=500), nullable=False),
        sa.Column(
            "request_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "identity_proof_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("requester_email_hash", sa.String(length=64), nullable=False),
        sa.Column("requester_email_masked", sa.String(length=320), nullable=False),
        sa.Column("assigned_cpo_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result_notice_email_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '10 days'"),
        ),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("result_summary", sa.Text()),
        sa.Column("result_notice_hash", sa.String(length=64)),
        sa.Column(
            "export_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "partial_response", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
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
        sa.PrimaryKeyConstraint("request_id", name="pk_dsr_requests"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_dsr_requests_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_cpo_user_id"],
            ["app.users.user_id"],
            name="fk_dsr_requests_assigned_cpo_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["result_notice_email_id"],
            ["app.email_queue.email_id"],
            name="fk_dsr_requests_result_notice_email_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "request_type IN ('access', 'correction', 'delete', 'suspend')",
            name="ck_dsr_requests_request_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'identity_check', 'processing', "
            "'completed', 'rejected', 'withdrawn')",
            name="ck_dsr_requests_status_allowed",
        ),
        schema="app",
    )
    op.create_index(
        "ix_dsr_requests_user_created",
        "dsr_requests",
        ["user_id", sa.text("created_at DESC")],
        schema="app",
    )
    op.create_index(
        "ix_dsr_requests_status_due",
        "dsr_requests",
        ["status", "due_at"],
        schema="app",
    )
    op.create_index(
        "ix_dsr_requests_type_status",
        "dsr_requests",
        ["request_type", "status"],
        schema="app",
    )
    op.create_index(
        "ix_dsr_requests_assigned_cpo",
        "dsr_requests",
        ["assigned_cpo_user_id"],
        schema="app",
        postgresql_where=sa.text("assigned_cpo_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_dsr_requests_open_due",
        "dsr_requests",
        ["due_at"],
        schema="app",
        postgresql_where=sa.text("status IN ('received', 'identity_check', 'processing')"),
    )
    op.execute(
        "CREATE TRIGGER trg_dsr_requests_touch_updated_at "
        "BEFORE UPDATE ON app.dsr_requests FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_dsr_requests_touch_updated_at ON app.dsr_requests")
    op.drop_index("ix_dsr_requests_open_due", table_name="dsr_requests", schema="app")
    op.drop_index("ix_dsr_requests_assigned_cpo", table_name="dsr_requests", schema="app")
    op.drop_index("ix_dsr_requests_type_status", table_name="dsr_requests", schema="app")
    op.drop_index("ix_dsr_requests_status_due", table_name="dsr_requests", schema="app")
    op.drop_index("ix_dsr_requests_user_created", table_name="dsr_requests", schema="app")
    op.drop_table("dsr_requests", schema="app")
