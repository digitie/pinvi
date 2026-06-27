"""trip file attachment quotas

Revision ID: 20260627_0026
Revises: 20260627_0025
Create Date: 2026-06-27 11:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260627_0026"
down_revision: str | None = "20260627_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "storage_settings",
        sa.Column(
            "attachment_max_upload_bytes",
            sa.BigInteger(),
            server_default=sa.text("10485760"),
            nullable=False,
        ),
        schema="app",
    )
    op.add_column(
        "storage_settings",
        sa.Column(
            "trip_attachment_quota_bytes",
            sa.BigInteger(),
            server_default=sa.text("104857600"),
            nullable=False,
        ),
        schema="app",
    )
    op.add_column(
        "storage_settings",
        sa.Column(
            "user_attachment_quota_bytes",
            sa.BigInteger(),
            server_default=sa.text("1073741824"),
            nullable=False,
        ),
        schema="app",
    )
    op.create_check_constraint(
        "ck_storage_settings_storage_settings_attachment_max_upload_bytes_positive",
        "storage_settings",
        "attachment_max_upload_bytes > 0",
        schema="app",
    )
    op.create_check_constraint(
        "ck_storage_settings_storage_settings_trip_attachment_quota_bytes_positive",
        "storage_settings",
        "trip_attachment_quota_bytes > 0",
        schema="app",
    )
    op.create_check_constraint(
        "ck_storage_settings_storage_settings_user_attachment_quota_bytes_positive",
        "storage_settings",
        "user_attachment_quota_bytes > 0",
        schema="app",
    )

    for column_name in (
        "attachment_max_upload_bytes_override",
        "trip_attachment_quota_bytes_override",
        "user_attachment_quota_bytes_override",
    ):
        op.add_column("users", sa.Column(column_name, sa.BigInteger()), schema="app")
        op.create_check_constraint(
            f"ck_users_{column_name}_positive",
            "users",
            f"{column_name} IS NULL OR {column_name} > 0",
            schema="app",
        )

    op.add_column(
        "curated_plan_attachments",
        sa.Column("trip_day_index", sa.Integer()),
        schema="app",
    )
    op.drop_constraint(
        "ck_curated_plan_attachments_single_target",
        "curated_plan_attachments",
        schema="app",
    )
    op.create_foreign_key(
        "fk_curated_plan_attachments_trip_day",
        "curated_plan_attachments",
        "trip_days",
        ["trip_id", "trip_day_index"],
        ["trip_id", "day_index"],
        source_schema="app",
        referent_schema="app",
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_curated_plan_attachments_single_target",
        "curated_plan_attachments",
        """
        (
          trip_id IS NOT NULL AND trip_day_index IS NULL AND trip_poi_id IS NULL
          AND curated_plan_id IS NULL AND curated_poi_id IS NULL
        ) OR (
          trip_id IS NOT NULL AND trip_day_index IS NOT NULL AND trip_poi_id IS NULL
          AND curated_plan_id IS NULL AND curated_poi_id IS NULL
        ) OR (
          trip_id IS NULL AND trip_day_index IS NULL AND trip_poi_id IS NOT NULL
          AND curated_plan_id IS NULL AND curated_poi_id IS NULL
        ) OR (
          trip_id IS NULL AND trip_day_index IS NULL AND trip_poi_id IS NULL
          AND curated_plan_id IS NOT NULL AND curated_poi_id IS NULL
        ) OR (
          trip_id IS NULL AND trip_day_index IS NULL AND trip_poi_id IS NULL
          AND curated_plan_id IS NULL AND curated_poi_id IS NOT NULL
        )
        """,
        schema="app",
    )
    op.create_index(
        "ix_curated_plan_attachments_trip_day",
        "curated_plan_attachments",
        ["trip_id", "trip_day_index", "sort_order"],
        schema="app",
        postgresql_where=sa.text(
            "trip_id IS NOT NULL AND trip_day_index IS NOT NULL AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curated_plan_attachments_trip_day",
        table_name="curated_plan_attachments",
        schema="app",
    )
    op.drop_constraint(
        "ck_curated_plan_attachments_single_target",
        "curated_plan_attachments",
        schema="app",
    )
    op.drop_constraint(
        "fk_curated_plan_attachments_trip_day",
        "curated_plan_attachments",
        schema="app",
        type_="foreignkey",
    )
    op.create_check_constraint(
        "ck_curated_plan_attachments_single_target",
        "curated_plan_attachments",
        "num_nonnulls(trip_id, trip_poi_id, curated_plan_id, curated_poi_id) = 1",
        schema="app",
    )
    op.drop_column("curated_plan_attachments", "trip_day_index", schema="app")

    for column_name in (
        "user_attachment_quota_bytes_override",
        "trip_attachment_quota_bytes_override",
        "attachment_max_upload_bytes_override",
    ):
        op.drop_constraint(f"ck_users_{column_name}_positive", "users", schema="app")
        op.drop_column("users", column_name, schema="app")

    op.drop_constraint(
        "ck_storage_settings_storage_settings_user_attachment_quota_bytes_positive",
        "storage_settings",
        schema="app",
    )
    op.drop_constraint(
        "ck_storage_settings_storage_settings_trip_attachment_quota_bytes_positive",
        "storage_settings",
        schema="app",
    )
    op.drop_constraint(
        "ck_storage_settings_storage_settings_attachment_max_upload_bytes_positive",
        "storage_settings",
        schema="app",
    )
    op.drop_column("storage_settings", "user_attachment_quota_bytes", schema="app")
    op.drop_column("storage_settings", "trip_attachment_quota_bytes", schema="app")
    op.drop_column("storage_settings", "attachment_max_upload_bytes", schema="app")
