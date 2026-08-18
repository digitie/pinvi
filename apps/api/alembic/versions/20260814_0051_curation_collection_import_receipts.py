"""canonical curation collection UUID provenance와 import receipt를 추가한다.

Map T-VN-40은 legacy curated-feature 복사 계약을 collection/item UUID snapshot으로
교체한다. 이 expand migration은 기존 열을 아직 제거하지 않으면서 새 provenance tuple과
actor-scoped idempotency receipt를 먼저 추가한다. receipt는 pending에서 completed로 한 번만
전이하며 입력·terminal 결과는 이후 변경할 수 없다.

Revision ID: 20260814_0051
Revises: 20260811_0050
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0051"
down_revision: str | None = "20260811_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK_TEMPLATE = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '{revision}'"
)

_IMPORT_RECEIPT_GUARD = """
CREATE FUNCTION app.guard_ktm_curation_import_receipt()
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
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_collection_id", postgresql.UUID(as_uuid=True)),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_collection_revision", sa.BigInteger()),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_collection_etag", sa.String(128)),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_item_set_hash_version", sa.String(64)),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_item_set_hash", sa.String(64)),
        schema="app",
    )
    op.add_column(
        "curated_trip_plans",
        sa.Column("source_curation_item_count", sa.BigInteger()),
        schema="app",
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
    op.create_index(
        "uq_curated_trip_plans_curation_collection_active",
        "curated_trip_plans",
        ["source_system", "source_curation_collection_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "deleted_at IS NULL AND source_system = 'kor-travel-map' "
            "AND source_curation_collection_id IS NOT NULL"
        ),
    )

    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curation_item_id", postgresql.UUID(as_uuid=True)),
        schema="app",
    )
    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curation_item_revision", sa.BigInteger()),
        schema="app",
    )
    op.add_column(
        "curated_plan_pois",
        sa.Column("source_curation_item_etag", sa.String(128)),
        schema="app",
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
    op.create_unique_constraint(
        "uq_curated_plan_pois_curation_item",
        "curated_plan_pois",
        ["curated_plan_id", "source_curation_item_id"],
        schema="app",
    )

    op.create_table(
        "ktm_curation_import_receipts",
        sa.Column(
            "receipt_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="kor-travel-map"),
        sa.Column("source_curation_collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_curation_collection_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_curation_collection_etag", sa.String(128), nullable=False),
        sa.Column("source_curation_item_set_hash_version", sa.String(64), nullable=False),
        sa.Column("source_curation_item_set_hash", sa.String(64), nullable=False),
        sa.Column("source_curation_item_count", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("requested_is_published", sa.Boolean()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("result_plan_id", postgresql.UUID(as_uuid=True)),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_ktm_curation_import_receipts_fingerprint",
        ),
        sa.CheckConstraint(
            "source_system = 'kor-travel-map' AND mode IN ('create', 'refresh')",
            name="ck_ktm_curation_import_receipts_request",
        ),
        sa.CheckConstraint(
            "source_curation_collection_revision > 0 AND "
            "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
            "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
            "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
            "source_curation_item_count BETWEEN 0 AND 2000",
            name="ck_ktm_curation_import_receipts_source",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND result_plan_id IS NULL AND response_status IS NULL "
            "AND response_body IS NULL AND completed_at IS NULL) OR "
            "(status = 'completed' AND result_plan_id IS NOT NULL "
            "AND response_status IN (200, 201) AND jsonb_typeof(response_body) = 'object' "
            "AND completed_at IS NOT NULL)",
            name="ck_ktm_curation_import_receipts_terminal",
        ),
        sa.ForeignKeyConstraint(
            ["actor_admin_id"],
            ["app.users.user_id"],
            name="fk_ktm_curation_import_receipts_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_plan_id"],
            ["app.curated_trip_plans.curated_plan_id"],
            name="fk_ktm_curation_import_receipts_result_plan",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("receipt_id", name="pk_ktm_curation_import_receipts"),
        sa.UniqueConstraint(
            "actor_admin_id",
            "idempotency_key",
            name="uq_ktm_curation_import_receipts_actor_key",
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_curation_import_receipts_collection_created",
        "ktm_curation_import_receipts",
        ["source_curation_collection_id", "created_at"],
        schema="app",
    )
    op.execute(sa.text(_IMPORT_RECEIPT_GUARD))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_import_receipt_row_guard "
            "BEFORE UPDATE OR DELETE ON app.ktm_curation_import_receipts "
            "FOR EACH ROW EXECUTE FUNCTION app.guard_ktm_curation_import_receipt()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_curation_import_receipt_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_curation_import_receipts "
            "FOR EACH STATEMENT EXECUTE FUNCTION app.guard_ktm_curation_import_receipt()"
        )
    )
    _repin_boundary_contract("20260814_0051")


def downgrade() -> None:
    _repin_boundary_contract("20260811_0050")
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_curation_import_receipt_truncate_guard "
            "ON app.ktm_curation_import_receipts"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_curation_import_receipt_row_guard "
            "ON app.ktm_curation_import_receipts"
        )
    )
    op.drop_table("ktm_curation_import_receipts", schema="app")
    op.execute(sa.text("DROP FUNCTION app.guard_ktm_curation_import_receipt()"))

    op.drop_constraint(
        "uq_curated_plan_pois_curation_item",
        "curated_plan_pois",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "ck_curated_plan_pois_curation_source",
        "curated_plan_pois",
        schema="app",
        type_="check",
    )
    op.drop_column("curated_plan_pois", "source_curation_item_etag", schema="app")
    op.drop_column("curated_plan_pois", "source_curation_item_revision", schema="app")
    op.drop_column("curated_plan_pois", "source_curation_item_id", schema="app")

    op.drop_index(
        "uq_curated_trip_plans_curation_collection_active",
        table_name="curated_trip_plans",
        schema="app",
    )
    op.drop_constraint(
        "ck_curated_trip_plans_curation_source",
        "curated_trip_plans",
        schema="app",
        type_="check",
    )
    op.drop_column("curated_trip_plans", "source_curation_item_count", schema="app")
    op.drop_column("curated_trip_plans", "source_curation_item_set_hash", schema="app")
    op.drop_column("curated_trip_plans", "source_curation_item_set_hash_version", schema="app")
    op.drop_column("curated_trip_plans", "source_curation_collection_etag", schema="app")
    op.drop_column("curated_trip_plans", "source_curation_collection_revision", schema="app")
    op.drop_column("curated_trip_plans", "source_curation_collection_id", schema="app")
