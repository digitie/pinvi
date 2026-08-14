"""canonical curation import의 causal provenance를 forward-only로 봉인한다.

0050/0051은 배포 가능한 revision이므로 그 파일을 고치지 않는다. 이 migration은 기존
0051 catalog를 실제 출발점으로 삼아 receipt/item causal chain, terminal correlation,
INSERT guard, consumer 문자열 상한을 추가한다. 0051에서 이미 생성된 provenance 중 exact
item receipt를 재구성할 수 없는 행은 추측하지 않고 upgrade를 중단한다.

Revision ID: 20260814_0052
Revises: 20260814_0051
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0052"
down_revision: str | None = "20260814_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK_TEMPLATE = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '{revision}'"
)

_IMPORT_RECEIPT_GUARD_V2 = """
CREATE OR REPLACE FUNCTION app.guard_ktm_curation_import_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_item_count bigint;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation import receipt is append-only' USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.result_plan_id IS NOT NULL
           OR NEW.response_status IS NOT NULL
           OR NEW.response_body IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'curation import receipt must start pending' USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation import receipt is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.source_curation_collection_id IS DISTINCT FROM OLD.source_curation_collection_id
       OR NEW.source_curation_collection_revision
          IS DISTINCT FROM OLD.source_curation_collection_revision
       OR NEW.source_curation_collection_etag
          IS DISTINCT FROM OLD.source_curation_collection_etag
       OR NEW.source_curation_item_set_hash_version
          IS DISTINCT FROM OLD.source_curation_item_set_hash_version
       OR NEW.source_curation_item_set_hash
          IS DISTINCT FROM OLD.source_curation_item_set_hash
       OR NEW.source_curation_item_count IS DISTINCT FROM OLD.source_curation_item_count
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.requested_is_published IS DISTINCT FROM OLD.requested_is_published
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation import request tuple is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'curation import receipt may only complete' USING ERRCODE = '55000';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM app.curated_trip_plans AS plan
         WHERE plan.curated_plan_id = NEW.result_plan_id
           AND plan.deleted_at IS NULL
           AND plan.source_system = NEW.source_system
           AND plan.source_curation_collection_id = NEW.source_curation_collection_id
           AND plan.source_curation_collection_revision =
               NEW.source_curation_collection_revision
           AND plan.source_curation_collection_etag = NEW.source_curation_collection_etag
           AND plan.source_curation_item_set_hash_version =
               NEW.source_curation_item_set_hash_version
           AND plan.source_curation_item_set_hash = NEW.source_curation_item_set_hash
           AND plan.source_curation_item_count = NEW.source_curation_item_count
           AND (
               NEW.requested_is_published IS NULL
               OR plan.is_published = NEW.requested_is_published
           )
    ) THEN
        RAISE EXCEPTION 'curation import receipt result plan proof does not match'
            USING ERRCODE = '23514';
    END IF;
    SELECT count(*)
      INTO v_item_count
      FROM app.ktm_curation_import_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id;
    IF v_item_count <> NEW.source_curation_item_count THEN
        RAISE EXCEPTION 'curation import receipt item set is incomplete' USING ERRCODE = '55000';
    END IF;
    IF (
        SELECT count(*)
          FROM app.curated_plan_pois AS poi
         WHERE poi.curated_plan_id = NEW.result_plan_id
           AND poi.deleted_at IS NULL
    ) <> v_item_count
       OR EXISTS (
           SELECT 1
             FROM app.ktm_curation_import_receipt_items AS item
             LEFT JOIN app.curated_plan_pois AS poi
               ON poi.curated_plan_id = NEW.result_plan_id
              AND poi.deleted_at IS NULL
              AND poi.source_curation_import_receipt_id = item.receipt_id
              AND poi.source_curation_collection_id = item.source_curation_collection_id
              AND poi.source_curation_item_id = item.source_curation_item_id
              AND poi.source_curation_item_revision = item.source_curation_item_revision
              AND poi.source_curation_item_etag = item.source_curation_item_etag
              AND poi.feature_uuid = item.feature_uuid
            WHERE item.receipt_id = NEW.receipt_id
              AND poi.curated_poi_id IS NULL
       )
    THEN
        RAISE EXCEPTION 'curation import receipt POI set does not match'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""

_IMPORT_RECEIPT_GUARD_V1 = """
CREATE OR REPLACE FUNCTION app.guard_ktm_curation_import_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation import receipt is append-only' USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation import receipt is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.source_curation_collection_id IS DISTINCT FROM OLD.source_curation_collection_id
       OR NEW.source_curation_collection_revision
          IS DISTINCT FROM OLD.source_curation_collection_revision
       OR NEW.source_curation_collection_etag
          IS DISTINCT FROM OLD.source_curation_collection_etag
       OR NEW.source_curation_item_set_hash_version
          IS DISTINCT FROM OLD.source_curation_item_set_hash_version
       OR NEW.source_curation_item_set_hash
          IS DISTINCT FROM OLD.source_curation_item_set_hash
       OR NEW.source_curation_item_count IS DISTINCT FROM OLD.source_curation_item_count
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.requested_is_published IS DISTINCT FROM OLD.requested_is_published
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation import request tuple is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'curation import receipt may only complete' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""

_IMPORT_RECEIPT_ITEM_GUARD = """
CREATE FUNCTION app.guard_ktm_curation_import_receipt_item()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    v_receipt_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation import receipt item is append-only' USING ERRCODE = '55000';
    END IF;
    SELECT receipt.status
      INTO v_receipt_status
      FROM app.ktm_curation_import_receipts AS receipt
     WHERE receipt.receipt_id = NEW.receipt_id
     FOR KEY SHARE;
    IF v_receipt_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'curation import receipt item requires pending receipt'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""

_RESTORE_ATTEMPT_GUARD_V2 = """
CREATE OR REPLACE FUNCTION app.guard_ktm_cache_target_restore_fence_attempt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'cache target restore fence attempt is append-only' USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.response_status IS NOT NULL
           OR NEW.response_etag IS NOT NULL
           OR NEW.response_body IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'cache target restore fence attempt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed cache target restore fence attempt is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.consumer_id IS DISTINCT FROM OLD.consumer_id
       OR NEW.external_system IS DISTINCT FROM OLD.external_system
       OR NEW.expected_restore_epoch IS DISTINCT FROM OLD.expected_restore_epoch
       OR NEW.expected_control_version IS DISTINCT FROM OLD.expected_control_version
       OR NEW.stream_etag IS DISTINCT FROM OLD.stream_etag
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'cache target restore fence pre-CAS tuple is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'cache target restore fence attempt may only complete' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""

_RESTORE_ATTEMPT_GUARD_V1 = _RESTORE_ATTEMPT_GUARD_V2.replace(
    "    IF TG_OP = 'INSERT' THEN\n"
    "        IF NEW.status <> 'pending'\n"
    "           OR NEW.response_status IS NOT NULL\n"
    "           OR NEW.response_etag IS NOT NULL\n"
    "           OR NEW.response_body IS NOT NULL\n"
    "           OR NEW.completed_at IS NOT NULL\n"
    "        THEN\n"
    "            RAISE EXCEPTION 'cache target restore fence attempt must start pending'\n"
    "                USING ERRCODE = '55000';\n"
    "        END IF;\n"
    "        RETURN NEW;\n"
    "    END IF;\n",
    "",
)


def _repin_boundary_contract(revision_value: str) -> None:
    op.drop_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK_TEMPLATE.format(revision=revision_value),
        schema="app",
    )


def _replace_row_trigger(table: str, trigger: str, events: str, function: str) -> None:
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON app.{table}"))
    op.execute(
        sa.text(
            f"CREATE TRIGGER {trigger} BEFORE {events} ON app.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION app.{function}()"
        )
    )


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM app.curated_plan_pois "
            "WHERE source_curation_item_id IS NOT NULL) THEN "
            "RAISE EXCEPTION '0052 cannot reconstruct existing item receipt provenance' "
            "USING ERRCODE = '23514'; END IF; "
            "IF EXISTS (SELECT 1 FROM app.ktm_curation_import_receipts "
            "WHERE status = 'completed' AND source_curation_item_count <> 0) THEN "
            "RAISE EXCEPTION '0052 cannot reconstruct completed non-empty receipt members' "
            "USING ERRCODE = '23514'; END IF; "
            "IF EXISTS ("
            "SELECT 1 FROM app.ktm_curation_import_receipts AS receipt "
            "LEFT JOIN app.curated_trip_plans AS plan "
            "ON plan.curated_plan_id = receipt.result_plan_id "
            "AND plan.source_curation_collection_id = "
            "receipt.source_curation_collection_id "
            "WHERE receipt.status = 'completed' AND ("
            "plan.curated_plan_id IS NULL OR plan.deleted_at IS NOT NULL "
            "OR plan.source_system IS DISTINCT FROM receipt.source_system "
            "OR plan.source_curation_collection_revision IS DISTINCT FROM "
            "receipt.source_curation_collection_revision "
            "OR plan.source_curation_collection_etag IS DISTINCT FROM "
            "receipt.source_curation_collection_etag "
            "OR plan.source_curation_item_set_hash_version IS DISTINCT FROM "
            "receipt.source_curation_item_set_hash_version "
            "OR plan.source_curation_item_set_hash IS DISTINCT FROM "
            "receipt.source_curation_item_set_hash "
            "OR plan.source_curation_item_count IS DISTINCT FROM 0 "
            "OR (receipt.requested_is_published IS NOT NULL AND "
            "plan.is_published IS DISTINCT FROM receipt.requested_is_published) "
            "OR receipt.response_body ->> 'notice_plan_id' "
            "IS DISTINCT FROM receipt.result_plan_id::text "
            "OR receipt.response_body ->> 'source_curation_collection_id' "
            "IS DISTINCT FROM receipt.source_curation_collection_id::text "
            "OR EXISTS (SELECT 1 FROM app.curated_plan_pois AS poi "
            "WHERE poi.curated_plan_id = receipt.result_plan_id "
            "AND poi.deleted_at IS NULL "
            "AND poi.source_curation_item_id IS NOT NULL))) THEN "
            "RAISE EXCEPTION '0052 existing completed receipt proof is inconsistent' "
            "USING ERRCODE = '23514'; END IF; END $$"
        )
    )

    op.alter_column(
        "curated_trip_plans",
        "title",
        existing_type=sa.String(200),
        type_=sa.String(300),
        existing_nullable=False,
        schema="app",
    )
    op.drop_constraint(
        "ck_curated_trip_plans_curation_source",
        "curated_trip_plans",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_curated_trip_plans_curation_source"),
        "curated_trip_plans",
        "num_nonnulls(source_curation_collection_id, "
        "source_curation_collection_revision, source_curation_collection_etag, "
        "source_curation_item_set_hash_version, source_curation_item_set_hash, "
        "source_curation_item_count) = 0 OR "
        "(source_system = 'kor-travel-map' AND "
        "num_nonnulls(source_curation_collection_id, "
        "source_curation_collection_revision, source_curation_collection_etag, "
        "source_curation_item_set_hash_version, source_curation_item_set_hash, "
        "source_curation_item_count) = 6 AND "
        "source_curation_collection_revision > 0 AND "
        "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
        "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
        "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
        "source_curation_item_count BETWEEN 0 AND 2000)",
        schema="app",
    )
    op.alter_column(
        "curated_trip_plans",
        "category",
        existing_type=sa.String(80),
        type_=sa.String(128),
        existing_nullable=False,
        existing_server_default="recommended",
        schema="app",
    )
    op.create_unique_constraint(
        "uq_curated_trip_plans_curation_identity",
        "curated_trip_plans",
        ["curated_plan_id", "source_curation_collection_id"],
        schema="app",
    )

    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curation_import_receipt_id", postgresql.UUID(as_uuid=True)),
        schema="app",
    )
    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curation_collection_id", postgresql.UUID(as_uuid=True)),
        schema="app",
    )
    op.drop_constraint(
        "ck_curated_plan_pois_curation_source",
        "curated_plan_pois",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_curated_plan_pois_curation_source"),
        "curated_plan_pois",
        "num_nonnulls(source_curation_import_receipt_id, "
        "source_curation_collection_id, source_curation_item_id, "
        "source_curation_item_revision, source_curation_item_etag) = 0 OR "
        "(num_nonnulls(source_curation_import_receipt_id, "
        "source_curation_collection_id, source_curation_item_id, "
        "source_curation_item_revision, source_curation_item_etag) = 5 AND "
        "feature_uuid IS NOT NULL AND source_curation_item_revision > 0 AND "
        "source_curation_item_etag ~ '^\"sha256:[0-9a-f]{64}\"$')",
        schema="app",
    )

    op.create_unique_constraint(
        "uq_ktm_curation_import_receipts_collection",
        "ktm_curation_import_receipts",
        ["receipt_id", "source_curation_collection_id"],
        schema="app",
    )
    op.drop_constraint(
        "fk_ktm_curation_import_receipts_result_plan",
        "ktm_curation_import_receipts",
        schema="app",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_ktm_curation_import_receipts_result_source",
        "ktm_curation_import_receipts",
        "curated_trip_plans",
        ["result_plan_id", "source_curation_collection_id"],
        ["curated_plan_id", "source_curation_collection_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    for constraint_name in (
        "ck_ktm_curation_import_receipts_fingerprint",
        "ck_ktm_curation_import_receipts_request",
        "ck_ktm_curation_import_receipts_source",
    ):
        op.drop_constraint(
            constraint_name,
            "ktm_curation_import_receipts",
            schema="app",
            type_="check",
        )
    op.create_check_constraint(
        op.f("ck_ktm_curation_import_receipts_fingerprint"),
        "ktm_curation_import_receipts",
        "request_fingerprint ~ '^[0-9a-f]{64}$'",
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_ktm_curation_import_receipts_request"),
        "ktm_curation_import_receipts",
        "source_system = 'kor-travel-map' AND mode IN ('create', 'refresh')",
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_ktm_curation_import_receipts_source"),
        "ktm_curation_import_receipts",
        "source_curation_collection_revision > 0 AND "
        "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
        "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
        "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
        "source_curation_item_count BETWEEN 0 AND 2000",
        schema="app",
    )
    op.drop_constraint(
        "ck_ktm_curation_import_receipts_terminal",
        "ktm_curation_import_receipts",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_curation_import_receipts_terminal"),
        "ktm_curation_import_receipts",
        "(status = 'pending' AND result_plan_id IS NULL AND response_status IS NULL "
        "AND response_body IS NULL AND completed_at IS NULL) OR "
        "(status = 'completed' AND result_plan_id IS NOT NULL "
        "AND response_status IN (200, 201) AND jsonb_typeof(response_body) = 'object' "
        "AND response_body ->> 'notice_plan_id' = result_plan_id::text "
        "AND response_body ->> 'source_curation_collection_id' = "
        "source_curation_collection_id::text AND completed_at IS NOT NULL)",
        schema="app",
    )
    op.create_table(
        "ktm_curation_import_receipt_items",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_curation_collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_curation_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_curation_item_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_curation_item_etag", sa.String(128), nullable=False),
        sa.Column("feature_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source_curation_item_revision > 0 AND "
            "source_curation_item_etag ~ '^\"sha256:[0-9a-f]{64}\"$'",
            name=op.f("ck_ktm_curation_import_receipt_items_source"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "source_curation_collection_id"],
            [
                "app.ktm_curation_import_receipts.receipt_id",
                "app.ktm_curation_import_receipts.source_curation_collection_id",
            ],
            name="fk_ktm_curation_import_receipt_items_receipt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "receipt_id",
            "source_curation_item_id",
            name="pk_ktm_curation_import_receipt_items",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "source_curation_collection_id",
            "source_curation_item_id",
            "source_curation_item_revision",
            "source_curation_item_etag",
            "feature_uuid",
            name="uq_ktm_curation_import_receipt_items_proof",
        ),
        schema="app",
    )
    op.create_foreign_key(
        "fk_curated_plan_pois_curation_parent",
        "curated_plan_pois",
        "curated_trip_plans",
        ["curated_plan_id", "source_curation_collection_id"],
        ["curated_plan_id", "source_curation_collection_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_curated_plan_pois_curation_receipt_item",
        "curated_plan_pois",
        "ktm_curation_import_receipt_items",
        [
            "source_curation_import_receipt_id",
            "source_curation_collection_id",
            "source_curation_item_id",
            "source_curation_item_revision",
            "source_curation_item_etag",
            "feature_uuid",
        ],
        [
            "receipt_id",
            "source_curation_collection_id",
            "source_curation_item_id",
            "source_curation_item_revision",
            "source_curation_item_etag",
            "feature_uuid",
        ],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )

    op.execute(sa.text(_IMPORT_RECEIPT_GUARD_V2))
    _replace_row_trigger(
        "ktm_curation_import_receipts",
        "trg_ktm_curation_import_receipt_row_guard",
        "INSERT OR UPDATE OR DELETE",
        "guard_ktm_curation_import_receipt",
    )
    op.execute(sa.text(_IMPORT_RECEIPT_ITEM_GUARD))
    _replace_row_trigger(
        "ktm_curation_import_receipt_items",
        "trg_ktm_curation_import_receipt_item_row_guard",
        "INSERT OR UPDATE OR DELETE",
        "guard_ktm_curation_import_receipt_item",
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_import_receipt_item_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_curation_import_receipt_items "
            "FOR EACH STATEMENT EXECUTE FUNCTION app.guard_ktm_curation_import_receipt_item()"
        )
    )

    op.execute(sa.text(_RESTORE_ATTEMPT_GUARD_V2))
    _replace_row_trigger(
        "ktm_cache_target_restore_fence_attempts",
        "trg_ktm_ct_restore_attempt_row_guard",
        "INSERT OR UPDATE OR DELETE",
        "guard_ktm_cache_target_restore_fence_attempt",
    )
    _repin_boundary_contract("20260814_0052")


def downgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM app.ktm_curation_import_receipt_items) "
            "OR EXISTS (SELECT 1 FROM app.curated_plan_pois "
            "WHERE source_curation_import_receipt_id IS NOT NULL "
            "OR source_curation_collection_id IS NOT NULL) THEN "
            "RAISE EXCEPTION '0052 downgrade would discard causal item provenance' "
            "USING ERRCODE = '23514'; END IF; "
            "IF EXISTS (SELECT 1 FROM app.curated_trip_plans "
            "WHERE char_length(title) > 200 OR char_length(category) > 80) THEN "
            "RAISE EXCEPTION '0052 downgrade would truncate plan text' "
            "USING ERRCODE = '22001'; END IF; END $$"
        )
    )
    _repin_boundary_contract("20260814_0051")

    op.execute(sa.text(_RESTORE_ATTEMPT_GUARD_V1))
    _replace_row_trigger(
        "ktm_cache_target_restore_fence_attempts",
        "trg_ktm_ct_restore_attempt_row_guard",
        "UPDATE OR DELETE",
        "guard_ktm_cache_target_restore_fence_attempt",
    )

    op.drop_constraint(
        "fk_curated_plan_pois_curation_receipt_item",
        "curated_plan_pois",
        schema="app",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_curated_plan_pois_curation_parent",
        "curated_plan_pois",
        schema="app",
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_curation_import_receipt_item_truncate_guard "
            "ON app.ktm_curation_import_receipt_items"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_curation_import_receipt_item_row_guard "
            "ON app.ktm_curation_import_receipt_items"
        )
    )
    op.drop_table("ktm_curation_import_receipt_items", schema="app")
    op.execute(sa.text("DROP FUNCTION app.guard_ktm_curation_import_receipt_item()"))

    op.execute(sa.text(_IMPORT_RECEIPT_GUARD_V1))
    _replace_row_trigger(
        "ktm_curation_import_receipts",
        "trg_ktm_curation_import_receipt_row_guard",
        "UPDATE OR DELETE",
        "guard_ktm_curation_import_receipt",
    )
    op.drop_constraint(
        op.f("ck_ktm_curation_import_receipts_terminal"),
        "ktm_curation_import_receipts",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ktm_curation_import_receipts_terminal",
        "ktm_curation_import_receipts",
        "(status = 'pending' AND result_plan_id IS NULL AND response_status IS NULL "
        "AND response_body IS NULL AND completed_at IS NULL) OR "
        "(status = 'completed' AND result_plan_id IS NOT NULL "
        "AND response_status IN (200, 201) AND jsonb_typeof(response_body) = 'object' "
        "AND completed_at IS NOT NULL)",
        schema="app",
    )
    for constraint_name, definition in (
        (
            "ck_ktm_curation_import_receipts_fingerprint",
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
        ),
        (
            "ck_ktm_curation_import_receipts_request",
            "source_system = 'kor-travel-map' AND mode IN ('create', 'refresh')",
        ),
        (
            "ck_ktm_curation_import_receipts_source",
            "source_curation_collection_revision > 0 AND "
            "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
            "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
            "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
            "source_curation_item_count BETWEEN 0 AND 2000",
        ),
    ):
        op.drop_constraint(
            op.f(constraint_name),
            "ktm_curation_import_receipts",
            schema="app",
            type_="check",
        )
        op.create_check_constraint(
            constraint_name,
            "ktm_curation_import_receipts",
            definition,
            schema="app",
        )
    op.drop_constraint(
        "fk_ktm_curation_import_receipts_result_source",
        "ktm_curation_import_receipts",
        schema="app",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_ktm_curation_import_receipts_result_plan",
        "ktm_curation_import_receipts",
        "curated_trip_plans",
        ["result_plan_id"],
        ["curated_plan_id"],
        source_schema="app",
        referent_schema="app",
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_ktm_curation_import_receipts_collection",
        "ktm_curation_import_receipts",
        schema="app",
        type_="unique",
    )

    op.drop_constraint(
        op.f("ck_curated_plan_pois_curation_source"),
        "curated_plan_pois",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_curated_plan_pois_curation_source",
        "curated_plan_pois",
        "num_nonnulls(source_curation_item_id, source_curation_item_revision, "
        "source_curation_item_etag) = 0 OR "
        "(num_nonnulls(source_curation_item_id, source_curation_item_revision, "
        "source_curation_item_etag) = 3 AND source_curation_item_revision > 0 AND "
        "source_curation_item_etag ~ '^\"sha256:[0-9a-f]{64}\"$')",
        schema="app",
    )
    op.drop_column("curated_plan_pois", "source_curation_collection_id", schema="app")
    op.drop_column("curated_plan_pois", "source_curation_import_receipt_id", schema="app")
    op.drop_constraint(
        "uq_curated_trip_plans_curation_identity",
        "curated_trip_plans",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_curated_trip_plans_curation_source"),
        "curated_trip_plans",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_curated_trip_plans_curation_source",
        "curated_trip_plans",
        "num_nonnulls(source_curation_collection_id, "
        "source_curation_collection_revision, source_curation_collection_etag, "
        "source_curation_item_set_hash_version, source_curation_item_set_hash, "
        "source_curation_item_count) = 0 OR "
        "(source_system = 'kor-travel-map' AND "
        "num_nonnulls(source_curation_collection_id, "
        "source_curation_collection_revision, source_curation_collection_etag, "
        "source_curation_item_set_hash_version, source_curation_item_set_hash, "
        "source_curation_item_count) = 6 AND "
        "source_curation_collection_revision > 0 AND "
        "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
        "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
        "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
        "source_curation_item_count BETWEEN 0 AND 2000)",
        schema="app",
    )
    op.alter_column(
        "curated_trip_plans",
        "category",
        existing_type=sa.String(128),
        type_=sa.String(80),
        existing_nullable=False,
        existing_server_default="recommended",
        schema="app",
    )
    op.alter_column(
        "curated_trip_plans",
        "title",
        existing_type=sa.String(300),
        type_=sa.String(200),
        existing_nullable=False,
        schema="app",
    )
