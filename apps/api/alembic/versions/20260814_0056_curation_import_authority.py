"""304 import proof의 authoritative source와 final boundary를 forward-only로 고정한다.

Revision ID: 20260814_0056
Revises: 20260814_0055
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0056"
down_revision: str | None = "20260814_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260814_0056'"
)

_TERMINAL_RESPONSE_GUARD = """
CREATE OR REPLACE FUNCTION app.guard_ktm_curation_import_receipt_response()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status = 'pending'
       AND NEW.status = 'completed'
       AND (
           jsonb_typeof(NEW.response_body -> 'not_modified') IS DISTINCT FROM 'boolean'
           OR NEW.response_body ->> 'notice_plan_id' IS DISTINCT FROM NEW.result_plan_id::text
           OR NEW.response_body ->> 'source_system' IS DISTINCT FROM NEW.source_system
           OR NEW.response_body ->> 'source_curation_collection_id'
              IS DISTINCT FROM NEW.source_curation_collection_id::text
           OR NEW.response_body ->> 'source_curation_collection_revision'
              IS DISTINCT FROM NEW.source_curation_collection_revision::text
           OR NEW.response_body ->> 'source_curation_collection_etag'
              IS DISTINCT FROM NEW.source_curation_collection_etag
           OR NEW.response_body ->> 'source_curation_item_set_hash_version'
              IS DISTINCT FROM NEW.source_curation_item_set_hash_version
           OR NEW.response_body ->> 'source_curation_item_set_hash'
              IS DISTINCT FROM NEW.source_curation_item_set_hash
           OR NEW.response_body ->> 'source_curation_item_count'
              IS DISTINCT FROM NEW.source_curation_item_count::text
       )
    THEN
        RAISE EXCEPTION 'curation import receipt response does not match source tuple'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""


def upgrade() -> None:
    op.execute(sa.text(_TERMINAL_RESPONSE_GUARD))
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
        "20260814_0056 downgrade would reopen canonical import proof authority"
    )
