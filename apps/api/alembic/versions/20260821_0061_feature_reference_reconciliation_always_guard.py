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

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260821_0061'"
)


def _repin_boundary_contract() -> None:
    """새 head에서만 final boundary가 열리도록 DB/service pin을 함께 전진시킨다."""

    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK,
        schema="app",
    )


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
    _repin_boundary_contract()


def downgrade() -> None:
    raise RuntimeError("T-VN-M05 append-only guard migration is forward-only")
