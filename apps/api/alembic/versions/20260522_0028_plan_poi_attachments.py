"""add plan and poi attachments

Revision ID: 20260522_0028
Revises: 20260521_0027
Create Date: 2026-05-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260522_0028"
down_revision: str | None = "20260521_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_poi_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True)),
        sa.Column("trip_poi_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notice_plan_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notice_poi_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("bucket", sa.String(length=80), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("public_url", sa.Text()),
        sa.Column("checksum_sha256", sa.String(length=64)),
        sa.Column("role", sa.String(length=40), nullable=False, server_default="attachment"),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
            ["notice_plan_id"],
            ["notice_plans.id"],
            name="fk_plan_poi_attachments_notice_plan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notice_poi_id"],
            ["notice_pois.id"],
            name="fk_plan_poi_attachments_notice_poi_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["plan_poi_attachments.id"],
            name="fk_plan_poi_attachments_source_attachment_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_plan_poi_attachments_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_poi_id"],
            ["trip_pois.id"],
            name="fk_plan_poi_attachments_trip_poi_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_plan_poi_attachments_uploaded_by_user_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_plan_poi_attachments"),
    )
    op.create_index(
        "ix_plan_poi_attachments_trip",
        "plan_poi_attachments",
        ["trip_id", "sort_order"],
    )
    op.create_index(
        "ix_plan_poi_attachments_trip_poi",
        "plan_poi_attachments",
        ["trip_poi_id", "sort_order"],
    )
    op.create_index(
        "ix_plan_poi_attachments_notice_plan",
        "plan_poi_attachments",
        ["notice_plan_id", "sort_order"],
    )
    op.create_index(
        "ix_plan_poi_attachments_notice_poi",
        "plan_poi_attachments",
        ["notice_poi_id", "sort_order"],
    )
    op.create_index(
        "ix_plan_poi_attachments_source",
        "plan_poi_attachments",
        ["source_attachment_id"],
    )
    op.create_index(
        "ix_plan_poi_attachments_storage_key",
        "plan_poi_attachments",
        ["bucket", "storage_key"],
    )
    op.create_index(
        "ix_plan_poi_attachments_uploaded_by",
        "plan_poi_attachments",
        ["uploaded_by_user_id"],
    )
    op.create_index(
        "ix_plan_poi_attachments_active",
        "plan_poi_attachments",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_plan_poi_attachments_active", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_uploaded_by", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_storage_key", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_source", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_notice_poi", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_notice_plan", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_trip_poi", table_name="plan_poi_attachments")
    op.drop_index("ix_plan_poi_attachments_trip", table_name="plan_poi_attachments")
    op.drop_table("plan_poi_attachments")
