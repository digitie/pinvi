"""#667: 30일 휴지통과 첨부 업로드 예약·객체 정리 큐."""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261105_0103"
down_revision: str | None = "20260917_0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102')"
_CHECK = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103')"

def _boundary(check: str) -> None:
    op.drop_constraint(op.f("ck_ktm_ct_boundary_contract"), "ktm_cache_target_boundary_audits", schema="app", type_="check")
    op.create_check_constraint(op.f("ck_ktm_ct_boundary_contract"), "ktm_cache_target_boundary_audits", check, schema="app")


def upgrade() -> None:
    op.add_column("trips", sa.Column("purge_started_at", sa.DateTime(timezone=True)), schema="app")
    op.add_column("curated_plan_attachments", sa.Column("purged_at", sa.DateTime(timezone=True)), schema="app")
    op.add_column("curated_plan_attachments", sa.Column("moderation_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")), schema="app")
    op.execute("""
        UPDATE app.curated_plan_attachments AS attachment SET moderation_hold = true
        WHERE attachment.deleted_at IS NOT NULL AND EXISTS (
            SELECT 1 FROM app.content_reports AS report
            JOIN app.content_moderation_actions AS hidden ON hidden.report_id = report.report_id
            WHERE report.target_type = 'attachment' AND report.target_id = attachment.attachment_id
              AND report.status <> 'restored' AND hidden.action IN ('hide', 'takedown')
              AND NOT EXISTS (
                SELECT 1 FROM app.content_moderation_actions AS restored
                WHERE restored.report_id = report.report_id AND restored.action = 'restore'
                  AND restored.created_at > hidden.created_at
              )
        )
    """)
    op.create_table(
        "attachment_upload_intents",
        sa.Column("bucket", sa.String(80), primary_key=True),
        sa.Column("storage_key", sa.String(1024), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_bytes", sa.BigInteger()),
        sa.Column("write_token", postgresql.UUID(as_uuid=True)),
        sa.Column("write_started_at", sa.DateTime(timezone=True)),
        sa.Column("registered_at", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("byte_size > 0", name="intent_size_positive"),
        schema="app",
    )
    op.create_index("ix_attachment_upload_intents_user_id", "attachment_upload_intents", ["user_id"], schema="app")
    op.create_index("ix_attachment_upload_intents_expires_at", "attachment_upload_intents", ["expires_at"], schema="app")
    op.create_table(
        "attachment_gc_objects",
        sa.Column("bucket", sa.String(80), primary_key=True),
        sa.Column("storage_key", sa.String(1024), primary_key=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.Text()),
        schema="app",
    )
    for suffix, column in [("uploader", "uploaded_by_user_id"), ("trip", "trip_id"), ("poi", "trip_poi_id")]:
        op.create_index("ix_attachment_retained_" + suffix, "curated_plan_attachments", [column],
            schema="app", postgresql_where=sa.text("purged_at IS NULL"), postgresql_include=["byte_size"])
    _boundary(_CHECK)


def downgrade() -> None:
    _boundary(_PRIOR)
    for suffix in ["uploader", "trip", "poi"]:
        op.drop_index("ix_attachment_retained_" + suffix, table_name="curated_plan_attachments", schema="app")
    op.drop_table("attachment_gc_objects", schema="app")
    op.drop_table("attachment_upload_intents", schema="app")
    op.drop_column("curated_plan_attachments", "moderation_hold", schema="app")
    op.drop_column("curated_plan_attachments", "purged_at", schema="app")
    op.drop_column("trips", "purge_started_at", schema="app")
