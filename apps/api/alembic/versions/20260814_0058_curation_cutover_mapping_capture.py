"""Map release별 local cutover mapping root를 하나로 고정한다.

Revision ID: 20260814_0058
Revises: 20260814_0057
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260814_0058"
down_revision: str | None = "20260814_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260814_0058'"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ktm_curation_cutover_mapping_receipts_map_release",
        "ktm_curation_cutover_mapping_receipts",
        ["map_release_revision"],
        schema="app",
    )
    op.drop_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK,
        schema="app",
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260814_0058 downgrade would reopen curation cutover mapping root ambiguity"
    )
