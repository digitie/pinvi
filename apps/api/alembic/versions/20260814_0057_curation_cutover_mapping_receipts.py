"""Map T-VN-40C identity export를 PinVi backfill receipt로 봉인한다.

Revision ID: 20260814_0057
Revises: 20260814_0056
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0057"
down_revision: str | None = "20260814_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260814_0057'"
)

_RECEIPT_GUARD = """
CREATE FUNCTION app.guard_ktm_curation_cutover_mapping_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_item_count bigint;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover mapping receipt is append-only'
            USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending' OR NEW.completed_at IS NOT NULL THEN
            RAISE EXCEPTION 'curation cutover mapping receipt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation cutover mapping receipt is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.map_release_revision IS DISTINCT FROM OLD.map_release_revision
       OR NEW.mapping_root_version IS DISTINCT FROM OLD.mapping_root_version
       OR NEW.mapping_root IS DISTINCT FROM OLD.mapping_root
       OR NEW.mapping_count IS DISTINCT FROM OLD.mapping_count
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation cutover mapping receipt input is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed' OR NEW.completed_at IS NULL THEN
        RAISE EXCEPTION 'curation cutover mapping receipt may only complete'
            USING ERRCODE = '55000';
    END IF;

    -- Item insert는 같은 receipt row를 FOR UPDATE로 잡는다. terminal 전 item set을
    -- 고정하고, terminal 뒤 member를 붙이는 race를 함께 직렬화한다.
    PERFORM 1
      FROM app.ktm_curation_cutover_mapping_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id
     ORDER BY item.legacy_curated_feature_id
     FOR UPDATE;

    SELECT count(*)
      INTO v_item_count
      FROM app.ktm_curation_cutover_mapping_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id;
    IF v_item_count <> NEW.mapping_count THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item set is incomplete'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""

_RECEIPT_ITEM_GUARD = """
CREATE FUNCTION app.guard_ktm_curation_cutover_mapping_receipt_item()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_receipt_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item is append-only'
            USING ERRCODE = '55000';
    END IF;

    SELECT receipt.status
      INTO v_receipt_status
      FROM app.ktm_curation_cutover_mapping_receipts AS receipt
     WHERE receipt.receipt_id = NEW.receipt_id
     FOR UPDATE;
    IF v_receipt_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item requires pending receipt'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""


def _repin_boundary_contract() -> None:
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


def upgrade() -> None:
    op.create_table(
        "ktm_curation_cutover_mapping_receipts",
        sa.Column(
            "receipt_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("map_release_revision", sa.String(length=40), nullable=False),
        sa.Column("mapping_root_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_root", sa.String(length=64), nullable=False),
        sa.Column("mapping_count", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "map_release_revision ~ '^[0-9a-f]{40}$'",
            name=op.f("ck_ktm_curation_cutover_mapping_receipts_release"),
        ),
        sa.CheckConstraint(
            "mapping_root_version = 'ktm-curation-cutover-mapping-v1' AND "
            "mapping_root ~ '^[0-9a-f]{64}$' AND mapping_count >= 0",
            name=op.f("ck_ktm_curation_cutover_mapping_receipts_root"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name=op.f("ck_ktm_curation_cutover_mapping_receipts_terminal"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_admin_id"],
            ["app.users.user_id"],
            name="fk_ktm_curation_cutover_mapping_receipts_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("receipt_id", name="pk_ktm_curation_cutover_mapping_receipts"),
        sa.UniqueConstraint(
            "map_release_revision",
            "mapping_root_version",
            "mapping_root",
            name="uq_ktm_curation_cutover_mapping_receipts_map_root",
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_curation_cutover_mapping_receipts_actor_created",
        "ktm_curation_cutover_mapping_receipts",
        ["actor_admin_id", "created_at"],
        schema="app",
    )
    op.create_table(
        "ktm_curation_cutover_mapping_receipt_items",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_curated_feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("curation_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mapping_kind", sa.String(length=32), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "mapping_kind IN "
            "('legacy_projection', 'official_membership', 'manual_membership') AND "
            "source_row_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_ktm_curation_cutover_mapping_receipt_items_source"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["app.ktm_curation_cutover_mapping_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_mapping_receipt_items_receipt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "receipt_id",
            "legacy_curated_feature_id",
            name="pk_ktm_curation_cutover_mapping_receipt_items",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "curation_item_id",
            name="uq_ktm_curation_cutover_mapping_receipt_items_curation_item",
        ),
        schema="app",
    )
    op.execute(sa.text(_RECEIPT_GUARD))
    op.execute(sa.text(_RECEIPT_ITEM_GUARD))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_mapping_receipts_guard "
            "BEFORE INSERT OR UPDATE OR DELETE ON "
            "app.ktm_curation_cutover_mapping_receipts "
            "FOR EACH ROW EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_mapping_receipt()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_mapping_receipts_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_curation_cutover_mapping_receipts "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_mapping_receipt()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_mapping_receipt_items_guard "
            "BEFORE INSERT OR UPDATE OR DELETE ON "
            "app.ktm_curation_cutover_mapping_receipt_items "
            "FOR EACH ROW EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_mapping_receipt_item()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_mapping_receipt_items_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_curation_cutover_mapping_receipt_items "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_mapping_receipt_item()"
        )
    )
    _repin_boundary_contract()


def downgrade() -> None:
    raise RuntimeError(
        "20260814_0057 downgrade would discard immutable cutover mapping evidence"
    )
