"""legacy Map plan의 canonical backfill command receipt를 forward-only로 봉인한다.

Revision ID: 20260814_0059
Revises: 20260814_0058
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0059"
down_revision: str | None = "20260814_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260814_0059'"
)

_BACKFILL_RECEIPT_GUARD = """
CREATE FUNCTION app.guard_ktm_curation_cutover_backfill_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_mapping_status text;
    v_import_status text;
    v_import_mode text;
    v_import_actor uuid;
    v_import_plan uuid;
    v_import_collection uuid;
    v_mapping_collection uuid;
    v_plan_legacy_id uuid;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover backfill receipt is append-only'
            USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.import_receipt_id IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'curation cutover backfill receipt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation cutover backfill receipt is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.mapping_receipt_id IS DISTINCT FROM OLD.mapping_receipt_id
       OR NEW.legacy_curated_feature_id IS DISTINCT FROM OLD.legacy_curated_feature_id
       OR NEW.curated_plan_id IS DISTINCT FROM OLD.curated_plan_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation cutover backfill receipt input is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed'
       OR NEW.import_receipt_id IS NULL
       OR NEW.completed_at IS NULL
    THEN
        RAISE EXCEPTION 'curation cutover backfill receipt may only complete'
            USING ERRCODE = '55000';
    END IF;

    SELECT mapping_receipt.status, mapping_item.collection_id
      INTO v_mapping_status, v_mapping_collection
      FROM app.ktm_curation_cutover_mapping_receipts AS mapping_receipt
      JOIN app.ktm_curation_cutover_mapping_receipt_items AS mapping_item
        ON mapping_item.receipt_id = mapping_receipt.receipt_id
     WHERE mapping_receipt.receipt_id = NEW.mapping_receipt_id
       AND mapping_item.legacy_curated_feature_id = NEW.legacy_curated_feature_id
     FOR UPDATE OF mapping_receipt, mapping_item;
    IF NOT FOUND OR v_mapping_status <> 'completed' THEN
        RAISE EXCEPTION 'curation cutover backfill requires completed mapping receipt'
            USING ERRCODE = '23514';
    END IF;

    SELECT import_receipt.status,
           import_receipt.mode,
           import_receipt.actor_admin_id,
           import_receipt.result_plan_id,
           import_receipt.source_curation_collection_id
      INTO v_import_status,
           v_import_mode,
           v_import_actor,
           v_import_plan,
           v_import_collection
      FROM app.ktm_curation_import_receipts AS import_receipt
     WHERE import_receipt.receipt_id = NEW.import_receipt_id
     FOR UPDATE;
    IF NOT FOUND
       OR v_import_status <> 'completed'
       OR v_import_mode <> 'cutover-backfill'
       OR v_import_actor <> NEW.actor_admin_id
       OR v_import_plan <> NEW.curated_plan_id
       OR v_import_collection <> v_mapping_collection
    THEN
        RAISE EXCEPTION 'curation cutover backfill import receipt does not match mapping'
            USING ERRCODE = '23514';
    END IF;

    SELECT CASE
             WHEN plan.source_curated_feature_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
             THEN plan.source_curated_feature_id::uuid
             ELSE NULL
           END
      INTO v_plan_legacy_id
      FROM app.curated_trip_plans AS plan
     WHERE plan.curated_plan_id = NEW.curated_plan_id
       AND plan.deleted_at IS NULL
     FOR UPDATE;
    IF NOT FOUND OR v_plan_legacy_id IS DISTINCT FROM NEW.legacy_curated_feature_id THEN
        RAISE EXCEPTION 'curation cutover backfill plan provenance does not match mapping'
            USING ERRCODE = '23514';
    END IF;

    -- Terminal seal과 legacy source POI 제거를 같은 parent/row lock 순서로 묶는다.
    PERFORM 1
      FROM app.curated_plan_pois AS poi
     WHERE poi.curated_plan_id = NEW.curated_plan_id
     ORDER BY poi.curated_poi_id
     FOR UPDATE;
    IF EXISTS (
        SELECT 1
          FROM app.curated_plan_pois AS poi
         WHERE poi.curated_plan_id = NEW.curated_plan_id
           AND poi.deleted_at IS NULL
           AND (
               poi.source_curated_feature_id IS NOT NULL
               OR poi.source_curated_feature_item_id IS NOT NULL
           )
    ) THEN
        RAISE EXCEPTION 'curation cutover backfill leaves active legacy source POI'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""


def _repin_boundary_contract() -> None:
    # 0048~0058은 metadata naming convention이 physical constraint name에도 한 번 더
    # 적용된 catalog와 exact name catalog가 모두 존재할 수 있다. definition으로 하나를
    # 찾고 제거한 뒤 0059부터는 op.f()의 exact physical name으로 수렴시킨다.
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                v_constraint_name text;
            BEGIN
                SELECT con.conname
                  INTO v_constraint_name
                  FROM pg_catalog.pg_constraint AS con
                  JOIN pg_catalog.pg_class AS relation ON relation.oid = con.conrelid
                  JOIN pg_catalog.pg_namespace AS namespace
                    ON namespace.oid = relation.relnamespace
                 WHERE namespace.nspname = 'app'
                   AND relation.relname = 'ktm_cache_target_boundary_audits'
                   AND con.contype = 'c'
                   AND pg_catalog.pg_get_constraintdef(con.oid, true)
                       LIKE '%pinvi-cache-target-final-boundary/v1%';
                IF v_constraint_name IS NULL THEN
                    RAISE EXCEPTION 'cache target boundary contract CHECK is missing'
                        USING ERRCODE = '23514';
                END IF;
                EXECUTE format(
                    'ALTER TABLE app.ktm_cache_target_boundary_audits DROP CONSTRAINT %I',
                    v_constraint_name
                );
            END;
            $$;
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK,
        schema="app",
    )


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_ktm_curation_import_receipts_request"),
        "ktm_curation_import_receipts",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_curation_import_receipts_request"),
        "ktm_curation_import_receipts",
        "source_system = 'kor-travel-map' AND "
        "mode IN ('create', 'refresh', 'cutover-backfill')",
        schema="app",
    )
    op.create_table(
        "ktm_curation_cutover_backfill_receipts",
        sa.Column(
            "receipt_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mapping_receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_curated_feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("curated_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_receipt_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_ktm_curation_cutover_backfill_receipts_fingerprint"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND import_receipt_id IS NULL AND completed_at IS NULL) OR "
            "(status = 'completed' AND import_receipt_id IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_ktm_curation_cutover_backfill_receipts_terminal"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_admin_id"],
            ["app.users.user_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_receipt_id"],
            ["app.ktm_curation_cutover_mapping_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_mapping",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_receipt_id", "legacy_curated_feature_id"],
            [
                "app.ktm_curation_cutover_mapping_receipt_items.receipt_id",
                "app.ktm_curation_cutover_mapping_receipt_items.legacy_curated_feature_id",
            ],
            name="fk_ktm_curation_cutover_backfill_receipts_mapping_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["curated_plan_id"],
            ["app.curated_trip_plans.curated_plan_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_plan",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_receipt_id"],
            ["app.ktm_curation_import_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_import",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "receipt_id",
            name="pk_ktm_curation_cutover_backfill_receipts",
        ),
        sa.UniqueConstraint(
            "actor_admin_id",
            "idempotency_key",
            name="uq_ktm_curation_cutover_backfill_receipts_actor_key",
        ),
        sa.UniqueConstraint(
            "curated_plan_id",
            name="uq_ktm_curation_cutover_backfill_receipts_plan",
        ),
        sa.UniqueConstraint(
            "import_receipt_id",
            name="uq_ktm_curation_cutover_backfill_receipts_import",
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_curation_cutover_backfill_receipts_mapping_created",
        "ktm_curation_cutover_backfill_receipts",
        ["mapping_receipt_id", "created_at"],
        schema="app",
    )
    op.execute(sa.text(_BACKFILL_RECEIPT_GUARD))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_backfill_receipts_guard "
            "BEFORE INSERT OR UPDATE OR DELETE ON "
            "app.ktm_curation_cutover_backfill_receipts "
            "FOR EACH ROW EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_backfill_receipt()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_cutover_backfill_receipts_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_curation_cutover_backfill_receipts "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.guard_ktm_curation_cutover_backfill_receipt()"
        )
    )
    _repin_boundary_contract()


def downgrade() -> None:
    raise RuntimeError(
        "20260814_0059 downgrade would discard canonical cutover backfill evidence"
    )
