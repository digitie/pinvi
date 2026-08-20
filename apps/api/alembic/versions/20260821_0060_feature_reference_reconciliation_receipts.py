"""Map M05 Feature 참조 조정의 PinVi final receipt와 blocked attempt를 봉인한다.

Revision ID: 20260821_0060
Revises: 20260814_0059
Create Date: 2026-08-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260821_0060"
down_revision: str | None = "20260814_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_GUARD = """
CREATE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$
"""


def _create_append_only_trigger(table_name: str) -> None:
    trigger = f"trg_{table_name}_append_only"
    truncate_trigger = f"trg_{table_name}_truncate_append_only"
    op.execute(
        sa.text(
            f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON "
            f"app.{table_name} FOR EACH ROW EXECUTE FUNCTION "
            "app.guard_ktm_feature_reference_reconciliation_append_only()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {truncate_trigger} BEFORE TRUNCATE ON app.{table_name} "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.guard_ktm_feature_reference_reconciliation_append_only()"
        )
    )


def upgrade() -> None:
    op.create_table(
        "ktm_feature_reference_reconciliation_delivery_attempts",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("block_fingerprint_sha256", sa.String(length=64)),
        sa.Column("observation_root_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_sequence > 0", name="ck_ktm_frr_attempt_sequence"),
        sa.CheckConstraint("event_sequence > 0", name="ck_ktm_frr_attempt_event_sequence"),
        sa.CheckConstraint("event_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ktm_frr_attempt_event_sha"),
        sa.CheckConstraint(
            "observation_root_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ktm_frr_attempt_observation_root",
        ),
        sa.CheckConstraint(
            "(status = 'blocked' AND block_fingerprint_sha256 IS NOT NULL) OR "
            "(status = 'applied' AND block_fingerprint_sha256 IS NULL)",
            name="ck_ktm_frr_attempt_status",
        ),
        sa.CheckConstraint(
            "block_fingerprint_sha256 IS NULL OR block_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ktm_frr_attempt_block_fingerprint",
        ),
        sa.PrimaryKeyConstraint(
            "event_id",
            "attempt_sequence",
            name="pk_ktm_feature_reference_reconciliation_delivery_attempts",
        ),
        sa.UniqueConstraint(
            "event_id", "attempt_sequence", name="uq_ktm_frr_attempt_event_sequence"
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_frr_attempt_event_observed",
        "ktm_feature_reference_reconciliation_delivery_attempts",
        ["event_id", "observed_at"],
        schema="app",
    )

    op.create_table(
        "ktm_feature_reference_reconciliation_applied_receipts",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_sha256", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("old_feature_id", sa.Text(), nullable=False),
        sa.Column("old_feature_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replacement_feature_id", sa.Text()),
        sa.Column("replacement_feature_uuid", postgresql.UUID(as_uuid=True)),
        sa.Column("impact_root_sha256", sa.String(length=64), nullable=False),
        sa.Column("impact_count", sa.BigInteger(), nullable=False),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("event_sequence > 0", name="ck_ktm_frr_receipt_event_sequence"),
        sa.CheckConstraint("event_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ktm_frr_receipt_event_sha"),
        sa.CheckConstraint("receipt_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ktm_frr_receipt_sha"),
        sa.CheckConstraint(
            "impact_root_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ktm_frr_receipt_impact_root"
        ),
        sa.CheckConstraint("impact_count >= 0", name="ck_ktm_frr_receipt_impact_count"),
        sa.CheckConstraint(
            "old_feature_id IS NOT NULL AND old_feature_uuid IS NOT NULL",
            name="ck_ktm_frr_receipt_old_pair",
        ),
        sa.CheckConstraint(
            "(replacement_feature_id IS NULL AND replacement_feature_uuid IS NULL) OR "
            "(replacement_feature_id IS NOT NULL AND replacement_feature_uuid IS NOT NULL)",
            name="ck_ktm_frr_receipt_replacement_pair",
        ),
        sa.CheckConstraint(
            "(action = 'rebind' AND replacement_feature_id IS NOT NULL) OR "
            "(action = 'detach' AND replacement_feature_id IS NULL)",
            name="ck_ktm_frr_receipt_action",
        ),
        sa.PrimaryKeyConstraint(
            "event_id", name="pk_ktm_feature_reference_reconciliation_applied_receipts"
        ),
        sa.UniqueConstraint("event_sequence", name="uq_ktm_frr_receipt_event_sequence"),
        sa.UniqueConstraint("event_sha256", name="uq_ktm_frr_receipt_event_sha"),
        sa.UniqueConstraint("receipt_sha256", name="uq_ktm_frr_receipt_sha"),
        schema="app",
    )

    op.create_table(
        "ktm_feature_reference_reconciliation_impacts",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("impact_index", sa.Integer(), nullable=False),
        sa.Column("target_relation", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_feature_id", sa.Text(), nullable=False),
        sa.Column("old_feature_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replacement_feature_id", sa.Text()),
        sa.Column("replacement_feature_uuid", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("impact_index >= 0", name="ck_ktm_frr_impact_index"),
        sa.CheckConstraint(
            "target_relation IN ('trip_day_pois', 'curated_plan_pois', 'feature_suggestions')",
            name="ck_ktm_frr_impact_target_relation",
        ),
        sa.CheckConstraint(
            "old_feature_id IS NOT NULL AND old_feature_uuid IS NOT NULL",
            name="ck_ktm_frr_impact_old_pair",
        ),
        sa.CheckConstraint(
            "(replacement_feature_id IS NULL AND replacement_feature_uuid IS NULL) OR "
            "(replacement_feature_id IS NOT NULL AND replacement_feature_uuid IS NOT NULL)",
            name="ck_ktm_frr_impact_replacement_pair",
        ),
        sa.CheckConstraint(
            "(outcome = 'rebind' AND replacement_feature_id IS NOT NULL) OR "
            "(outcome = 'detach' AND replacement_feature_id IS NULL) OR "
            "outcome = 'already_reconciled'",
            name="ck_ktm_frr_impact_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["app.ktm_feature_reference_reconciliation_applied_receipts.event_id"],
            name="fk_ktm_frr_impact_receipt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "event_id", "impact_index", name="pk_ktm_feature_reference_reconciliation_impacts"
        ),
        sa.UniqueConstraint("event_id", "impact_index", name="uq_ktm_frr_impact_index"),
        sa.UniqueConstraint(
            "event_id", "target_relation", "target_id", name="uq_ktm_frr_impact_target"
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_frr_impact_target",
        "ktm_feature_reference_reconciliation_impacts",
        ["target_relation", "target_id"],
        schema="app",
    )

    op.execute(sa.text(_APPEND_ONLY_GUARD))
    for table_name in (
        "ktm_feature_reference_reconciliation_delivery_attempts",
        "ktm_feature_reference_reconciliation_applied_receipts",
        "ktm_feature_reference_reconciliation_impacts",
    ):
        _create_append_only_trigger(table_name)


def downgrade() -> None:
    raise RuntimeError("T-VN-M05 evidence migration is forward-only")
