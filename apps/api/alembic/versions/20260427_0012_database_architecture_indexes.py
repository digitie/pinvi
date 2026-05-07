"""add database architecture support indexes

Revision ID: 20260427_0012
Revises: 20260426_0011
Create Date: 2026-04-27 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260427_0012"
down_revision: str | None = "20260426_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_admin_notifications_etl_run_log_id",
        "admin_notifications",
        ["etl_run_log_id"],
    )
    op.create_index(
        "ix_tg_sys_outbox_etl_run_log_id",
        "telegram_system_notification_outbox",
        ["etl_run_log_id"],
    )
    op.create_index(
        "ix_rsb_address_code_standard_code",
        "region_serving_boundary",
        ["address_code_standard_code"],
    )
    op.create_index(
        "ix_rsb_import_batch_id",
        "region_serving_boundary",
        ["import_batch_id"],
    )
    op.create_index(
        "ix_rsb_raw_boundary_id",
        "region_serving_boundary",
        ["raw_boundary_id"],
    )
    op.create_index("ix_wska_stn_id", "weather_serving_kma_alert", ["stn_id"])


def downgrade() -> None:
    op.drop_index("ix_wska_stn_id", table_name="weather_serving_kma_alert")
    op.drop_index("ix_rsb_raw_boundary_id", table_name="region_serving_boundary")
    op.drop_index("ix_rsb_import_batch_id", table_name="region_serving_boundary")
    op.drop_index(
        "ix_rsb_address_code_standard_code",
        table_name="region_serving_boundary",
    )
    op.drop_index(
        "ix_tg_sys_outbox_etl_run_log_id",
        table_name="telegram_system_notification_outbox",
    )
    op.drop_index("ix_admin_notifications_etl_run_log_id", table_name="admin_notifications")
