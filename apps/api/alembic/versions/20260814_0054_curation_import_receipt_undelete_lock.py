"""기적용 0053 DB에도 canonical POI undelete lock을 forward 적용한다.

Revision ID: 20260814_0054
Revises: 20260814_0053
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0054"
down_revision: str | None = "20260814_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK_TEMPLATE = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '{revision}'"
)

_IMPORT_RECEIPT_GUARD_V4 = """
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

    PERFORM 1
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
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'curation import receipt result plan proof does not match'
            USING ERRCODE = '23514';
    END IF;

    -- deleted row도 잠가 completion 직후 concurrent undelete가 exact set을 깨지 못하게 한다.
    PERFORM 1
      FROM app.curated_plan_pois AS poi
     WHERE poi.curated_plan_id = NEW.result_plan_id
       AND poi.source_curation_item_id IS NOT NULL
     ORDER BY poi.curated_poi_id
     FOR UPDATE;

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
           AND poi.source_curation_item_id IS NOT NULL
    ) <> v_item_count
       OR EXISTS (
           SELECT 1
             FROM app.ktm_curation_import_receipt_items AS item
             LEFT JOIN app.curated_plan_pois AS poi
               ON poi.curated_plan_id = NEW.result_plan_id
              AND poi.deleted_at IS NULL
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

_IMPORT_RECEIPT_GUARD_V3 = _IMPORT_RECEIPT_GUARD_V4.replace(
    "     WHERE poi.curated_plan_id = NEW.result_plan_id\n"
    "       AND poi.source_curation_item_id IS NOT NULL\n"
    "     ORDER BY poi.curated_poi_id\n",
    "     WHERE poi.curated_plan_id = NEW.result_plan_id\n"
    "       AND poi.deleted_at IS NULL\n"
    "       AND poi.source_curation_item_id IS NOT NULL\n"
    "     ORDER BY poi.curated_poi_id\n",
    1,
)

_IMPORT_RECEIPT_ITEM_GUARD_V2 = """
CREATE OR REPLACE FUNCTION app.guard_ktm_curation_import_receipt_item()
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
     FOR UPDATE;
    IF v_receipt_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'curation import receipt item requires pending receipt'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""


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


def upgrade() -> None:
    op.execute(sa.text(_IMPORT_RECEIPT_GUARD_V4))
    op.execute(sa.text(_IMPORT_RECEIPT_ITEM_GUARD_V2))
    _repin_boundary_contract("20260814_0054")


def downgrade() -> None:
    _repin_boundary_contract("20260814_0053")
    op.execute(sa.text(_IMPORT_RECEIPT_ITEM_GUARD_V2))
    op.execute(sa.text(_IMPORT_RECEIPT_GUARD_V3))
