"""request-bound reconciliation expectation을 generic snapshot과 분리한다.

Revision ID: 20260801_0047
Revises: 20260801_0046
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260801_0047"
down_revision: str | None = "20260801_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ktm_cache_target_reconciliation_expectations",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_system", sa.String(length=32), server_default="pinvi", nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("restore_epoch", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_count", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_merkle_root", sa.LargeBinary(), nullable=False),
        sa.Column("high_watermark_cursor", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("receipt_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "external_system = 'pinvi'",
            name="ck_ktm_ct_reconcile_expectations_system",
        ),
        sa.CheckConstraint(
            "restore_epoch > 0",
            name="ck_ktm_ct_reconcile_expectations_epoch",
        ),
        sa.CheckConstraint(
            "snapshot_count >= 0",
            name="ck_ktm_ct_reconcile_expectations_count",
        ),
        sa.CheckConstraint(
            "octet_length(snapshot_merkle_root) = 32",
            name="ck_ktm_ct_reconcile_expectations_root",
        ),
        sa.CheckConstraint(
            "length(high_watermark_cursor) > 0",
            name="ck_ktm_ct_reconcile_expectations_cursor",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'received', 'invalidated')",
            name="ck_ktm_ct_reconcile_expectations_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND receipt_event_id IS NULL AND resolved_at IS NULL) OR "
            "(status = 'received' AND receipt_event_id IS NOT NULL AND resolved_at IS NOT NULL) OR "
            "(status = 'invalidated' AND receipt_event_id IS NULL AND resolved_at IS NOT NULL)",
            name="ck_ktm_ct_reconcile_expectations_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_event_id"],
            ["app.ktm_cache_target_events.event_id"],
            name="fk_ktm_ct_reconcile_expectations_receipt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "request_id", name="pk_ktm_cache_target_reconciliation_expectations"
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            name="uq_ktm_ct_reconcile_expectations_snapshot",
        ),
        sa.UniqueConstraint(
            "receipt_event_id",
            name="uq_ktm_ct_reconcile_expectations_receipt",
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_ct_reconcile_expectations_pending",
        "ktm_cache_target_reconciliation_expectations",
        ["external_system", "restore_epoch", "created_at"],
        unique=False,
        schema="app",
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ktm_ct_reconcile_expectations_pending",
        table_name="ktm_cache_target_reconciliation_expectations",
        schema="app",
    )
    op.drop_table("ktm_cache_target_reconciliation_expectations", schema="app")
