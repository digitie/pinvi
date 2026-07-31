"""cache target event payload receipt와 stream order 불변식

Revision ID: 20260731_0043
Revises: 20260731_0042
Create Date: 2026-07-31 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0043"
down_revision: str | None = "20260731_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ktm_cache_target_events",
        sa.Column("payload_fingerprint", sa.LargeBinary(), nullable=False),
        schema="app",
    )
    op.create_check_constraint(
        "ck_ktm_ct_events_payload_fingerprint",
        "ktm_cache_target_events",
        "octet_length(payload_fingerprint) = 32",
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_events_stream_order",
        "ktm_cache_target_events",
        ["external_system", "restore_epoch", "relay_order"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ktm_ct_events_stream_order",
        "ktm_cache_target_events",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "ck_ktm_ct_events_payload_fingerprint",
        "ktm_cache_target_events",
        schema="app",
        type_="check",
    )
    op.drop_column("ktm_cache_target_events", "payload_fingerprint", schema="app")
