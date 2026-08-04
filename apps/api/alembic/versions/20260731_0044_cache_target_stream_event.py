"""cache_target.reconciled stream event의 nullable target tuple

Revision ID: 20260731_0044
Revises: 20260731_0043
Create Date: 2026-07-31 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.sql.elements import conv

from alembic import op

revision: str = "20260731_0044"
down_revision: str | None = "20260731_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_ktm_ct_events_target_sequence",
        "ktm_cache_target_events",
        schema="app",
        type_="unique",
    )
    for constraint in (
        "ck_ktm_ct_events_generation",
        "ck_ktm_ct_events_sequence",
        "ck_ktm_ct_events_fingerprint",
    ):
        op.drop_constraint(conv(constraint), "ktm_cache_target_events", schema="app", type_="check")
    for column in (
        "target_key",
        "source_generation",
        "target_sequence",
        "source_payload_fingerprint",
    ):
        op.alter_column("ktm_cache_target_events", column, schema="app", nullable=True)
    op.create_check_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        "(event_type = 'cache_target.reconciled' AND target_key IS NULL AND target_id IS NULL "
        "AND source_generation IS NULL AND target_sequence IS NULL AND source_payload_fingerprint IS NULL) OR "
        "(event_type <> 'cache_target.reconciled' AND target_key IS NOT NULL AND source_generation > 0 "
        "AND target_sequence > 0 AND octet_length(source_payload_fingerprint) = 32)",
        schema="app",
    )
    op.create_index(
        "uq_ktm_ct_events_target_sequence",
        "ktm_cache_target_events",
        ["external_system", "target_key", "restore_epoch", "source_generation", "target_sequence"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("target_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ktm_ct_events_target_sequence", table_name="ktm_cache_target_events", schema="app"
    )
    op.drop_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        schema="app",
        type_="check",
    )
    for column in (
        "target_key",
        "source_generation",
        "target_sequence",
        "source_payload_fingerprint",
    ):
        op.alter_column("ktm_cache_target_events", column, schema="app", nullable=False)
    op.create_check_constraint(
        conv("ck_ktm_ct_events_generation"),
        "ktm_cache_target_events",
        "source_generation > 0",
        schema="app",
    )
    op.create_check_constraint(
        conv("ck_ktm_ct_events_sequence"),
        "ktm_cache_target_events",
        "target_sequence > 0",
        schema="app",
    )
    op.create_check_constraint(
        conv("ck_ktm_ct_events_fingerprint"),
        "ktm_cache_target_events",
        "octet_length(source_payload_fingerprint) = 32",
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_events_target_sequence",
        "ktm_cache_target_events",
        ["external_system", "target_key", "restore_epoch", "source_generation", "target_sequence"],
        schema="app",
    )
