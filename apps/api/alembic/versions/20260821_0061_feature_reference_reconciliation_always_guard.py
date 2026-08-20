"""M05 append-only evidence trigger를 replication bypass에도 항상 실행한다.

Revision ID: 20260821_0061
Revises: 20260821_0060
Create Date: 2026-08-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0061"
down_revision: str | None = "20260821_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in (
        "ktm_feature_reference_reconciliation_delivery_attempts",
        "ktm_feature_reference_reconciliation_applied_receipts",
        "ktm_feature_reference_reconciliation_impacts",
    ):
        for trigger_name in (
            f"trg_{table_name}_append_only",
            f"trg_{table_name}_truncate_append_only",
        ):
            op.execute(
                sa.text(f"ALTER TABLE app.{table_name} ENABLE ALWAYS TRIGGER {trigger_name}")
            )


def downgrade() -> None:
    raise RuntimeError("T-VN-M05 append-only guard migration is forward-only")
