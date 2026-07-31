"""stream reconciliation receipt의 snapshot fingerprint를 필수화한다.

Revision ID: 20260801_0046
Revises: 20260731_0045
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.sql.elements import conv

from alembic import op

revision: str = "20260801_0046"
down_revision: str | None = "20260731_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        schema="app",
        type_="check",
    )
    op.execute(
        """
        UPDATE app.ktm_cache_target_events
        SET source_payload_fingerprint = decode(
            CASE
                WHEN payload ->> 'expected_merkle_root' ~ '^[0-9a-f]{64}$'
                 AND payload ->> 'actual_merkle_root' = payload ->> 'expected_merkle_root'
                THEN payload ->> 'expected_merkle_root'
                WHEN payload ->> 'merkle_root' ~ '^[0-9a-f]{64}$'
                THEN payload ->> 'merkle_root'
            END,
            'hex'
        )
        WHERE event_type = 'cache_target.reconciled'
          AND source_payload_fingerprint IS NULL
        """
    )
    op.alter_column(
        "ktm_cache_target_events",
        "source_payload_fingerprint",
        schema="app",
        nullable=False,
    )
    op.create_check_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        "octet_length(source_payload_fingerprint) = 32 AND ("
        "(event_type = 'cache_target.reconciled' AND target_key IS NULL AND target_id IS NULL "
        "AND source_generation IS NULL AND target_sequence IS NULL) OR "
        "(event_type <> 'cache_target.reconciled' AND target_key IS NOT NULL "
        "AND target_id IS NOT NULL AND source_generation > 0 AND target_sequence > 0))",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        schema="app",
        type_="check",
    )
    op.alter_column(
        "ktm_cache_target_events",
        "source_payload_fingerprint",
        schema="app",
        nullable=True,
    )
    op.execute(
        """
        UPDATE app.ktm_cache_target_events
        SET source_payload_fingerprint = NULL
        WHERE event_type = 'cache_target.reconciled'
        """
    )
    op.create_check_constraint(
        conv("ck_ktm_ct_events_scope_tuple"),
        "ktm_cache_target_events",
        "(event_type = 'cache_target.reconciled' AND target_key IS NULL AND target_id IS NULL "
        "AND source_generation IS NULL AND target_sequence IS NULL "
        "AND source_payload_fingerprint IS NULL) OR "
        "(event_type <> 'cache_target.reconciled' AND target_key IS NOT NULL "
        "AND source_generation > 0 AND target_sequence > 0 "
        "AND octet_length(source_payload_fingerprint) = 32)",
        schema="app",
    )
