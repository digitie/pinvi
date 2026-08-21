"""T-VN-40 canonical collection provenance와 import receipt를 실제 DB에서 검증한다."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationCutoverBackfillReceipt,
    KtmCurationImportReceipt,
    KtmCurationImportReceiptItem,
)
from app.models.user import User
from app.services.curation_collection_import import (
    CurationCollectionImportConflict,
    _apply_not_modified,
    curation_collection_request_fingerprint,
    inspect_curation_collection_import,
)

pytestmark = pytest.mark.asyncio

API_DIR = Path(__file__).resolve().parents[2]
_COLLECTION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ITEM_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_ETAG = '"sha256:' + ("a" * 64) + '"'
_ITEM_SET_HASH = "b" * 64
_FINGERPRINT = "c" * 64


def _terminal_response(
    receipt: KtmCurationImportReceipt,
    plan_id: uuid.UUID,
    *,
    created_plan: bool,
    not_modified: bool = False,
) -> dict[str, object]:
    """terminal receipt guard가 요구하는 source tuple 전체를 만든다."""

    return {
        "notice_plan_id": str(plan_id),
        "created_plan": created_plan,
        "not_modified": not_modified,
        "source_system": receipt.source_system,
        "source_curation_collection_id": str(receipt.source_curation_collection_id),
        "source_curation_collection_revision": str(receipt.source_curation_collection_revision),
        "source_curation_collection_etag": receipt.source_curation_collection_etag,
        "source_curation_item_set_hash_version": (receipt.source_curation_item_set_hash_version),
        "source_curation_item_set_hash": receipt.source_curation_item_set_hash,
        "source_curation_item_count": receipt.source_curation_item_count,
        "copied_poi_count": 0,
        "removed_poi_count": 0,
    }


def _alembic(database_url: str, *args: str) -> None:
    env = dict(os.environ)
    env["PINVI_DATABASE_URL"] = database_url
    result = subprocess.run(  # noqa: S603
        ["alembic", *args],  # noqa: S607 -- repository venv의 고정 CLI
        cwd=API_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} 실패:\n{result.stdout}\n{result.stderr}")


async def _assert_0053_catalog_contract(db: AsyncSession) -> None:
    assert CuratedTripPlan.__table__.c.title.type.length == 300
    assert CuratedTripPlan.__table__.c.category.type.length == 128
    assert {
        constraint.name
        for constraint in CuratedTripPlan.__table__.constraints
        if constraint.name is not None and "curation" in constraint.name
    } == {
        "ck_curated_trip_plans_curation_source",
        "uq_curated_trip_plans_curation_identity",
    }
    assert {
        constraint.name
        for constraint in CuratedPlanPoi.__table__.constraints
        if constraint.name is not None and "curation" in constraint.name
    } == {
        "ck_curated_plan_pois_curation_source",
        "fk_curated_plan_pois_curation_parent",
        "fk_curated_plan_pois_curation_receipt_item",
        "uq_curated_plan_pois_curation_item",
    }
    assert {
        constraint.name
        for constraint in KtmCurationImportReceipt.__table__.constraints
        if constraint.name is not None
    } == {
        "ck_ktm_curation_import_receipts_fingerprint",
        "ck_ktm_curation_import_receipts_request",
        "ck_ktm_curation_import_receipts_source",
        "ck_ktm_curation_import_receipts_terminal",
        "fk_ktm_curation_import_receipts_actor",
        "fk_ktm_curation_import_receipts_result_source",
        "pk_ktm_curation_import_receipts",
        "uq_ktm_curation_import_receipts_actor_key",
        "uq_ktm_curation_import_receipts_collection",
    }
    assert {
        constraint.name
        for constraint in KtmCurationImportReceiptItem.__table__.constraints
        if constraint.name is not None
    } == {
        "ck_ktm_curation_import_receipt_items_source",
        "fk_ktm_curation_import_receipt_items_receipt",
        "pk_ktm_curation_import_receipt_items",
        "uq_ktm_curation_import_receipt_items_proof",
    }

    column_rows = (
        await db.execute(
            text(
                "SELECT c.relname || '.' || a.attname, "
                "pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull "
                "FROM pg_catalog.pg_attribute AS a "
                "JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'app' AND a.attnum > 0 AND NOT a.attisdropped "
                "AND c.relname IN ('curated_trip_plans', 'curated_plan_pois', "
                "'ktm_curation_import_receipts', "
                "'ktm_curation_import_receipt_items') "
                "AND (a.attname LIKE 'source_curation_%' OR "
                "c.relname IN ('ktm_curation_import_receipts', "
                "'ktm_curation_import_receipt_items'))"
            )
        )
    ).all()
    columns = {name: (data_type, not_null) for name, data_type, not_null in column_rows}
    assert columns == {
        "curated_trip_plans.source_curation_collection_id": ("uuid", False),
        "curated_trip_plans.source_curation_collection_revision": ("bigint", False),
        "curated_trip_plans.source_curation_collection_etag": (
            "character varying(128)",
            False,
        ),
        "curated_trip_plans.source_curation_item_set_hash_version": (
            "character varying(64)",
            False,
        ),
        "curated_trip_plans.source_curation_item_set_hash": (
            "character varying(64)",
            False,
        ),
        "curated_trip_plans.source_curation_item_count": ("bigint", False),
        "curated_plan_pois.source_curation_item_id": ("uuid", False),
        "curated_plan_pois.source_curation_item_revision": ("bigint", False),
        "curated_plan_pois.source_curation_item_etag": ("character varying(128)", False),
        "curated_plan_pois.source_curation_import_receipt_id": ("uuid", False),
        "curated_plan_pois.source_curation_collection_id": ("uuid", False),
        "ktm_curation_import_receipts.receipt_id": ("uuid", True),
        "ktm_curation_import_receipts.actor_admin_id": ("uuid", True),
        "ktm_curation_import_receipts.idempotency_key": ("uuid", True),
        "ktm_curation_import_receipts.request_fingerprint": (
            "character varying(64)",
            True,
        ),
        "ktm_curation_import_receipts.source_system": ("character varying(32)", True),
        "ktm_curation_import_receipts.source_curation_collection_id": ("uuid", True),
        "ktm_curation_import_receipts.source_curation_collection_revision": (
            "bigint",
            True,
        ),
        "ktm_curation_import_receipts.source_curation_collection_etag": (
            "character varying(128)",
            True,
        ),
        "ktm_curation_import_receipts.source_curation_item_set_hash_version": (
            "character varying(64)",
            True,
        ),
        "ktm_curation_import_receipts.source_curation_item_set_hash": (
            "character varying(64)",
            True,
        ),
        "ktm_curation_import_receipts.source_curation_item_count": ("bigint", True),
        "ktm_curation_import_receipts.mode": ("character varying(16)", True),
        "ktm_curation_import_receipts.requested_is_published": ("boolean", False),
        "ktm_curation_import_receipts.status": ("character varying(16)", True),
        "ktm_curation_import_receipts.result_plan_id": ("uuid", False),
        "ktm_curation_import_receipts.response_status": ("integer", False),
        "ktm_curation_import_receipts.response_body": ("jsonb", False),
        "ktm_curation_import_receipts.completed_at": (
            "timestamp with time zone",
            False,
        ),
        "ktm_curation_import_receipts.created_at": ("timestamp with time zone", True),
        "ktm_curation_import_receipts.updated_at": ("timestamp with time zone", True),
        "ktm_curation_import_receipt_items.receipt_id": ("uuid", True),
        "ktm_curation_import_receipt_items.source_curation_collection_id": ("uuid", True),
        "ktm_curation_import_receipt_items.source_curation_item_id": ("uuid", True),
        "ktm_curation_import_receipt_items.source_curation_item_revision": ("bigint", True),
        "ktm_curation_import_receipt_items.source_curation_item_etag": (
            "character varying(128)",
            True,
        ),
        "ktm_curation_import_receipt_items.feature_uuid": ("uuid", True),
        "ktm_curation_import_receipt_items.created_at": ("timestamp with time zone", True),
        "ktm_curation_import_receipt_items.updated_at": ("timestamp with time zone", True),
    }

    constraints = dict(
        (
            await db.execute(
                text(
                    "SELECT con.conname, pg_catalog.pg_get_constraintdef(con.oid, true) "
                    "FROM pg_catalog.pg_constraint AS con "
                    "JOIN pg_catalog.pg_namespace AS n ON n.oid = con.connamespace "
                    "WHERE n.nspname = 'app' AND con.conname = ANY(:names)"
                ),
                {
                    "names": [
                        "ck_curated_trip_plans_curation_source",
                        "ck_curated_plan_pois_curation_source",
                        "uq_curated_plan_pois_curation_item",
                        "fk_curated_plan_pois_curation_parent",
                        "fk_curated_plan_pois_curation_receipt_item",
                        "uq_curated_trip_plans_curation_identity",
                        "ck_ktm_curation_import_receipts_fingerprint",
                        "ck_ktm_curation_import_receipts_request",
                        "ck_ktm_curation_import_receipts_source",
                        "ck_ktm_curation_import_receipts_terminal",
                        "fk_ktm_curation_import_receipts_actor",
                        "fk_ktm_curation_import_receipts_result_source",
                        "pk_ktm_curation_import_receipts",
                        "uq_ktm_curation_import_receipts_actor_key",
                        "uq_ktm_curation_import_receipts_collection",
                        "ck_ktm_curation_import_receipt_items_source",
                        "fk_ktm_curation_import_receipt_items_receipt",
                        "pk_ktm_curation_import_receipt_items",
                        "uq_ktm_curation_import_receipt_items_proof",
                    ]
                },
            )
        ).all()
    )
    assert set(constraints) == {
        "ck_curated_trip_plans_curation_source",
        "ck_curated_plan_pois_curation_source",
        "uq_curated_plan_pois_curation_item",
        "fk_curated_plan_pois_curation_parent",
        "fk_curated_plan_pois_curation_receipt_item",
        "uq_curated_trip_plans_curation_identity",
        "ck_ktm_curation_import_receipts_fingerprint",
        "ck_ktm_curation_import_receipts_request",
        "ck_ktm_curation_import_receipts_source",
        "ck_ktm_curation_import_receipts_terminal",
        "fk_ktm_curation_import_receipts_actor",
        "fk_ktm_curation_import_receipts_result_source",
        "pk_ktm_curation_import_receipts",
        "uq_ktm_curation_import_receipts_actor_key",
        "uq_ktm_curation_import_receipts_collection",
        "ck_ktm_curation_import_receipt_items_source",
        "fk_ktm_curation_import_receipt_items_receipt",
        "pk_ktm_curation_import_receipt_items",
        "uq_ktm_curation_import_receipt_items_proof",
    }
    assert "source_curation_item_count >= 0" in constraints["ck_curated_trip_plans_curation_source"]
    assert (
        "source_curation_item_count <= 2000" in constraints["ck_curated_trip_plans_curation_source"]
    )
    assert (
        "source_curation_item_revision > 0" in constraints["ck_curated_plan_pois_curation_source"]
    )
    assert constraints["uq_curated_plan_pois_curation_item"] == (
        "UNIQUE (curated_plan_id, source_curation_item_id)"
    )
    request_definition = constraints["ck_ktm_curation_import_receipts_request"]
    assert "mode::text = ANY" in request_definition
    assert "'create'" in request_definition
    assert "'refresh'" in request_definition
    assert "'cutover-backfill'" in request_definition
    assert (
        "response_status = ANY (ARRAY[200, 201])"
        in constraints["ck_ktm_curation_import_receipts_terminal"]
    )
    assert constraints["fk_ktm_curation_import_receipts_actor"].startswith(
        "FOREIGN KEY (actor_admin_id) REFERENCES app.users(user_id)"
    )
    assert constraints["fk_ktm_curation_import_receipts_result_source"].startswith(
        "FOREIGN KEY (result_plan_id, source_curation_collection_id) "
        "REFERENCES app.curated_trip_plans(curated_plan_id, source_curation_collection_id)"
    )
    assert (
        "response_body ->> 'notice_plan_id'::text"
        in constraints["ck_ktm_curation_import_receipts_terminal"]
    )
    assert (
        "source_curation_item_revision > 0"
        in constraints["ck_ktm_curation_import_receipt_items_source"]
    )
    boundary_definition = await db.scalar(
        text(
            "SELECT pg_catalog.pg_get_constraintdef(con.oid, true) "
            "FROM pg_catalog.pg_constraint AS con "
            "JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'app' "
            "AND c.relname = 'ktm_cache_target_boundary_audits' "
            "AND pg_catalog.pg_get_constraintdef(con.oid, true) "
            "LIKE '%pinvi-cache-target-final-boundary/v1%'"
        )
    )
    assert boundary_definition is not None
    assert "schema_revision = '20260814_0059'::text" in boundary_definition

    indexes = dict(
        (
            await db.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_catalog.pg_indexes "
                    "WHERE schemaname = 'app' AND indexname = ANY(:names)"
                ),
                {
                    "names": [
                        "uq_curated_trip_plans_curation_collection_active",
                        "ix_ktm_curation_import_receipts_collection_created",
                    ]
                },
            )
        ).all()
    )
    assert set(indexes) == {
        "uq_curated_trip_plans_curation_collection_active",
        "ix_ktm_curation_import_receipts_collection_created",
    }
    assert "UNIQUE INDEX" in indexes["uq_curated_trip_plans_curation_collection_active"]
    assert (
        "source_curation_collection_id IS NOT NULL"
        in indexes["uq_curated_trip_plans_curation_collection_active"]
    )
    assert (
        "(source_curation_collection_id, created_at)"
        in indexes["ix_ktm_curation_import_receipts_collection_created"]
    )
    guard_definition = await db.scalar(
        text(
            "SELECT pg_catalog.pg_get_functiondef(p.oid) "
            "FROM pg_catalog.pg_proc AS p "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'app' "
            "AND p.proname = 'guard_ktm_curation_import_receipt'"
        )
    )
    assert guard_definition is not None
    normalized_guard = " ".join(guard_definition.split())
    assert (
        "FROM app.curated_plan_pois AS poi WHERE poi.curated_plan_id = "
        "NEW.result_plan_id AND poi.source_curation_item_id IS NOT NULL "
        "ORDER BY poi.curated_poi_id FOR UPDATE"
    ) in normalized_guard


async def _assert_0059_cutover_backfill_catalog_contract(db: AsyncSession) -> None:
    expected_constraint_names = {
        "ck_ktm_curation_cutover_backfill_receipts_fingerprint",
        "ck_ktm_curation_cutover_backfill_receipts_terminal",
        "fk_ktm_curation_cutover_backfill_receipts_actor",
        "fk_ktm_curation_cutover_backfill_receipts_import",
        "fk_ktm_curation_cutover_backfill_receipts_mapping",
        "fk_ktm_curation_cutover_backfill_receipts_mapping_item",
        "fk_ktm_curation_cutover_backfill_receipts_plan",
        "pk_ktm_curation_cutover_backfill_receipts",
        "uq_ktm_curation_cutover_backfill_receipts_actor_key",
        "uq_ktm_curation_cutover_backfill_receipts_import",
        "uq_ktm_curation_cutover_backfill_receipts_plan",
    }
    assert {
        constraint.name
        for constraint in KtmCurationCutoverBackfillReceipt.__table__.constraints
        if constraint.name is not None
    } == expected_constraint_names
    constraints = dict(
        (
            await db.execute(
                text(
                    "SELECT con.conname, pg_catalog.pg_get_constraintdef(con.oid, true) "
                    "FROM pg_catalog.pg_constraint AS con "
                    "JOIN pg_catalog.pg_class AS relation ON relation.oid = con.conrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'app' "
                    "AND relation.relname = 'ktm_curation_cutover_backfill_receipts'"
                )
            )
        ).all()
    )
    assert set(constraints) == expected_constraint_names
    assert (
        "request_fingerprint::text ~"
        in constraints["ck_ktm_curation_cutover_backfill_receipts_fingerprint"]
    )
    assert (
        "status::text = 'pending'::text"
        in constraints["ck_ktm_curation_cutover_backfill_receipts_terminal"]
    )
    assert constraints["fk_ktm_curation_cutover_backfill_receipts_mapping_item"].startswith(
        "FOREIGN KEY (mapping_receipt_id, legacy_curated_feature_id) "
        "REFERENCES app.ktm_curation_cutover_mapping_receipt_items"
    )
    assert constraints["fk_ktm_curation_cutover_backfill_receipts_import"].startswith(
        "FOREIGN KEY (import_receipt_id) REFERENCES app.ktm_curation_import_receipts"
    )
    guard_definition = await db.scalar(
        text(
            "SELECT pg_catalog.pg_get_functiondef(p.oid) "
            "FROM pg_catalog.pg_proc AS p "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'app' "
            "AND p.proname = 'guard_ktm_curation_cutover_backfill_receipt'"
        )
    )
    assert guard_definition is not None
    normalized_guard = " ".join(guard_definition.split())
    assert "v_import_mode <> 'cutover-backfill'" in normalized_guard
    assert "curation cutover backfill leaves active legacy source POI" in normalized_guard
    assert "ORDER BY poi.curated_poi_id FOR UPDATE" in normalized_guard


async def test_tvn40_cutover_backfill_receipt_catalog_is_exact(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        await _assert_0059_cutover_backfill_catalog_contract(db)


async def test_tvn40_curation_receipt_catalog_is_exact_and_detects_semantic_drift(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        await _assert_0053_catalog_contract(db)
        await db.execute(
            text(
                "ALTER TABLE app.curated_trip_plans "
                "DROP CONSTRAINT ck_curated_trip_plans_curation_source"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE app.curated_trip_plans "
                "ADD CONSTRAINT ck_curated_trip_plans_curation_source CHECK (true)"
            )
        )
        with pytest.raises(AssertionError):
            await _assert_0053_catalog_contract(db)
        await db.rollback()


async def test_existing_0051_schema_and_data_upgrade_forward_to_0053(
    _database_url: str,
) -> None:
    # 0056부터 downgrade가 forward-only로 fail-close한다. 같은 disposable
    # integration DB에서 app schema만 다시 만들고 실제 0051→head를 검증한다.
    reset_engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with reset_engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA app CASCADE"))
            await connection.execute(text("CREATE SCHEMA app"))
        _alembic(_database_url, "upgrade", "20260814_0051")
        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass('app.ktm_curation_import_receipts')")
                    )
                    == "app.ktm_curation_import_receipts"
                )
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass('app.ktm_curation_import_receipt_items')")
                    )
                    is None
                )
                widths = dict(
                    (
                        await connection.execute(
                            text(
                                "SELECT column_name, character_maximum_length "
                                "FROM information_schema.columns "
                                "WHERE table_schema = 'app' "
                                "AND table_name = 'curated_trip_plans' "
                                "AND column_name IN ('title', 'category')"
                            )
                        )
                    ).all()
                )
                assert widths == {"category": 80, "title": 200}
                poi_causal_column_count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'app' AND table_name = 'curated_plan_pois' "
                        "AND column_name IN ('source_curation_import_receipt_id', "
                        "'source_curation_collection_id')"
                    )
                )
                assert poi_causal_column_count == 0
                actor_id = uuid.uuid4()
                plan_id = uuid.uuid4()
                receipt_id = uuid.uuid4()
                idempotency_key = uuid.uuid4()
                await connection.execute(
                    text("INSERT INTO app.users (user_id, email) VALUES (:actor_id, :email)"),
                    {"actor_id": actor_id, "email": f"old-0051-{actor_id}@pinvi.test"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO app.curated_trip_plans ("
                        "curated_plan_id, slug, title, category, source_system, "
                        "source_curation_collection_id, source_curation_collection_revision, "
                        "source_curation_collection_etag, source_curation_item_set_hash_version, "
                        "source_curation_item_set_hash, source_curation_item_count, "
                        "created_by_admin_id, updated_by_admin_id) VALUES ("
                        ":plan_id, :slug, '구 0051 정본', 'recommended', 'kor-travel-map', "
                        ":collection_id, 1, :etag, 'ktm-db-item-set-v1', :item_hash, 0, "
                        ":actor_id, :actor_id)"
                    ),
                    {
                        "plan_id": plan_id,
                        "slug": f"old-0051-{plan_id}",
                        "collection_id": _COLLECTION_ID,
                        "etag": _ETAG,
                        "item_hash": _ITEM_SET_HASH,
                        "actor_id": actor_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO app.ktm_curation_import_receipts ("
                        "receipt_id, actor_admin_id, idempotency_key, request_fingerprint, "
                        "source_curation_collection_id, source_curation_collection_revision, "
                        "source_curation_collection_etag, source_curation_item_set_hash_version, "
                        "source_curation_item_set_hash, source_curation_item_count, mode, "
                        "requested_is_published, status, result_plan_id, response_status, "
                        "response_body, completed_at) VALUES ("
                        ":receipt_id, :actor_id, :idempotency_key, :fingerprint, "
                        ":collection_id, 1, :etag, 'ktm-db-item-set-v1', :item_hash, 0, "
                        "'create', false, 'completed', :plan_id, 201, "
                        "CAST(:response_body AS jsonb), now())"
                    ),
                    {
                        "receipt_id": receipt_id,
                        "actor_id": actor_id,
                        "idempotency_key": idempotency_key,
                        "fingerprint": curation_collection_request_fingerprint(
                            collection_id=_COLLECTION_ID,
                            mode="create",
                            is_published=False,
                        ),
                        "collection_id": _COLLECTION_ID,
                        "etag": _ETAG,
                        "item_hash": _ITEM_SET_HASH,
                        "plan_id": plan_id,
                        "response_body": json.dumps(
                            {
                                "notice_plan_id": str(plan_id),
                                # 0056 전에는 JSON type guard가 없어 coercible string이
                                # terminal history에 남을 수 있었다. replay는 이를
                                # bool/int로 조용히 정규화하지 않고 typed conflict여야 한다.
                                "created_plan": "true",
                                "not_modified": "false",
                                "source_system": "kor-travel-map",
                                "source_curation_collection_id": str(_COLLECTION_ID),
                                "source_curation_collection_revision": "1",
                                "source_curation_collection_etag": _ETAG,
                                "source_curation_item_set_hash_version": ("ktm-db-item-set-v1"),
                                "source_curation_item_set_hash": _ITEM_SET_HASH,
                                "source_curation_item_count": "0",
                                "copied_poi_count": "0",
                                "removed_poi_count": "0",
                            }
                        ),
                    },
                )
                manual_poi_id = await connection.scalar(
                    text(
                        "INSERT INTO app.curated_plan_pois ("
                        "curated_plan_id, sort_order, feature_uuid, feature_snapshot) "
                        "VALUES (:plan_id, 'manual', :feature_uuid, '{}'::jsonb) "
                        "RETURNING curated_poi_id"
                    ),
                    {"plan_id": plan_id, "feature_uuid": uuid.uuid4()},
                )
        finally:
            await engine.dispose()

        _alembic(_database_url, "upgrade", "head")
        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass('app.ktm_curation_import_receipt_items')")
                    )
                    == "app.ktm_curation_import_receipt_items"
                )
                widths = dict(
                    (
                        await connection.execute(
                            text(
                                "SELECT column_name, character_maximum_length "
                                "FROM information_schema.columns "
                                "WHERE table_schema = 'app' "
                                "AND table_name = 'curated_trip_plans' "
                                "AND column_name IN ('title', 'category')"
                            )
                        )
                    ).all()
                )
                assert widths == {"category": 128, "title": 300}
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM app.ktm_curation_import_receipts "
                            "WHERE receipt_id = :receipt_id AND status = 'completed'"
                        ),
                        {"receipt_id": receipt_id},
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM app.curated_plan_pois "
                            "WHERE curated_poi_id = :poi_id "
                            "AND source_curation_item_id IS NULL"
                        ),
                        {"poi_id": manual_poi_id},
                    )
                    == 1
                )
                trigger_definition = await connection.scalar(
                    text(
                        "SELECT pg_catalog.pg_get_triggerdef(oid, true) "
                        "FROM pg_catalog.pg_trigger "
                        "WHERE tgname = 'trg_ktm_curation_import_receipt_row_guard'"
                    )
                )
                assert trigger_definition is not None
                assert "BEFORE INSERT OR DELETE OR UPDATE" in trigger_definition
            async with AsyncSession(engine) as db:
                orm_plan = await db.scalar(
                    select(CuratedTripPlan).where(CuratedTripPlan.curated_plan_id == plan_id)
                )
                assert orm_plan is not None
                assert orm_plan.source_curation_collection_id == _COLLECTION_ID
                orm_pois = (await db.scalars(select(CuratedPlanPoi))).all()
                assert [poi.curated_poi_id for poi in orm_pois] == [manual_poi_id]
                assert orm_pois[0].source_curation_item_id is None
                with pytest.raises(
                    CurationCollectionImportConflict,
                    match="현재 계약에 맞지 않습니다",
                ):
                    await inspect_curation_collection_import(
                        db,
                        actor_admin_id=actor_id,
                        idempotency_key=idempotency_key,
                        collection_id=_COLLECTION_ID,
                        mode="create",
                        is_published=False,
                    )
                fresh_receipt = KtmCurationImportReceipt(
                    actor_admin_id=actor_id,
                    idempotency_key=uuid.uuid4(),
                    request_fingerprint=curation_collection_request_fingerprint(
                        collection_id=_COLLECTION_ID,
                        mode="refresh",
                        is_published=False,
                    ),
                    source_curation_collection_id=_COLLECTION_ID,
                    source_curation_collection_revision=1,
                    source_curation_collection_etag=_ETAG,
                    source_curation_item_set_hash_version="ktm-db-item-set-v1",
                    source_curation_item_set_hash=_ITEM_SET_HASH,
                    source_curation_item_count=0,
                    mode="refresh",
                    requested_is_published=False,
                )
                db.add(fresh_receipt)
                await db.flush()
                with pytest.raises(
                    CurationCollectionImportConflict,
                    match="immutable import proof가 없습니다",
                ):
                    await _apply_not_modified(
                        db,
                        receipt=fresh_receipt,
                        plan=orm_plan,
                        source_etag=_ETAG,
                    )
                assert (
                    await db.scalar(
                        select(KtmCurationImportReceiptItem).where(
                            KtmCurationImportReceiptItem.receipt_id == fresh_receipt.receipt_id
                        )
                    )
                    is None
                )
                await db.rollback()
        finally:
            await engine.dispose()
    finally:
        try:
            _alembic(_database_url, "upgrade", "head")
        finally:
            await reset_engine.dispose()


async def _seed_admin(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        admin = User(
            email=f"admin-{uuid.uuid4().hex}@pinvi.test",
            password_hash=None,
            nickname="관리자",
            status="active",
            roles=["admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        return admin.user_id


async def test_existing_0053_database_receives_0054_undelete_lock(
    _database_url: str,
) -> None:
    """구 0053 catalog가 forward upgrade에서 V4 lock을 받는다."""

    engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            old_definition = await connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_functiondef(p.oid) "
                    "FROM pg_catalog.pg_proc AS p "
                    "JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'app' "
                    "AND p.proname = 'guard_ktm_curation_import_receipt'"
                )
            )
            assert old_definition is not None
            old_definition = old_definition.replace(
                "     WHERE poi.curated_plan_id = NEW.result_plan_id\n"
                "       AND poi.source_curation_item_id IS NOT NULL\n",
                "     WHERE poi.curated_plan_id = NEW.result_plan_id\n"
                "       AND poi.deleted_at IS NULL\n"
                "       AND poi.source_curation_item_id IS NOT NULL\n",
                1,
            )
            assert "poi.deleted_at IS NULL" in old_definition
            await connection.execute(text(old_definition))
            # 이 regression은 head DB에서 historical 0053 catalog를 의도적으로
            # 합성한다. 0057 이후의 mapping/backfill receipt와 M05 evidence
            # relation/function은 0053에는 없었다. 후속 migration이 실제 CREATE
            # 경로를 다시 실행하도록 먼저 모두 제거한다.
            await connection.execute(
                text(
                    "DROP TABLE app.ktm_feature_reference_reconciliation_impacts, "
                    "app.ktm_feature_reference_reconciliation_applied_receipts, "
                    "app.ktm_feature_reference_reconciliation_delivery_attempts"
                )
            )
            await connection.execute(
                text("DROP FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only()")
            )
            await connection.execute(text("DROP TABLE app.ktm_curation_cutover_backfill_receipts"))
            await connection.execute(
                text(
                    "DROP TABLE app.ktm_curation_cutover_mapping_receipt_items, "
                    "app.ktm_curation_cutover_mapping_receipts"
                )
            )
            await connection.execute(
                text(
                    "DROP FUNCTION "
                    "app.guard_ktm_curation_cutover_mapping_receipt(), "
                    "app.guard_ktm_curation_cutover_mapping_receipt_item(), "
                    "app.guard_ktm_curation_cutover_backfill_receipt()"
                )
            )
            # 0054가 적용되기 직전의 catalog에는 naming convention이 physical
            # CHECK 이름에 다시 적용돼 있었다. 0059의 exact-name 수렴 이후 head
            # catalog를 0053으로만 stamp하면 0054의 drop 대상이 없어지므로, 이
            # synthetic historical state에서는 당시 CHECK 정의와 물리명을 함께
            # 복원한다.
            await connection.execute(
                text(
                    """
                    DO $$
                    DECLARE
                        v_constraint_name text;
                    BEGIN
                        SELECT con.conname
                          INTO v_constraint_name
                          FROM pg_catalog.pg_constraint AS con
                          JOIN pg_catalog.pg_class AS relation
                            ON relation.oid = con.conrelid
                          JOIN pg_catalog.pg_namespace AS namespace
                            ON namespace.oid = relation.relnamespace
                         WHERE namespace.nspname = 'app'
                           AND relation.relname = 'ktm_cache_target_boundary_audits'
                           AND con.contype = 'c'
                           AND pg_catalog.pg_get_constraintdef(con.oid, true)
                               LIKE '%pinvi-cache-target-final-boundary/v1%';
                        IF v_constraint_name IS NULL THEN
                            RAISE EXCEPTION 'cache target boundary CHECK is missing';
                        END IF;
                        EXECUTE format(
                            'ALTER TABLE app.ktm_cache_target_boundary_audits '
                            'DROP CONSTRAINT %I',
                            v_constraint_name
                        );
                    END;
                    $$;
                    """
                )
            )
            await connection.execute(
                text(
                    "ALTER TABLE app.ktm_cache_target_boundary_audits "
                    "ADD CONSTRAINT "
                    "ck_ktm_cache_target_boundary_audits_"
                    "ck_ktm_ct_boundary_contract "
                    "CHECK (contract_version = 'pinvi-cache-target-final-boundary/v1' "
                    "AND status = 'succeeded' "
                    "AND schema_revision = '20260814_0053')"
                )
            )
            await connection.execute(
                text("UPDATE app.alembic_version SET version_num = '20260814_0053'")
            )
    finally:
        await engine.dispose()

    try:
        _alembic(_database_url, "upgrade", "head")
        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260821_0061"
                )
                new_body = await connection.scalar(
                    text(
                        "SELECT prosrc FROM pg_catalog.pg_proc AS p "
                        "JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'app' "
                        "AND p.proname = 'guard_ktm_curation_import_receipt'"
                    )
                )
                assert new_body is not None
                lock_clause = new_body.split("SELECT count(*)", maxsplit=1)[0]
                assert "poi.source_curation_item_id IS NOT NULL" in lock_clause
                assert "poi.deleted_at IS NULL" not in lock_clause
        finally:
            await engine.dispose()
    finally:
        _alembic(_database_url, "upgrade", "head")


async def test_conditional_snapshot_rejects_legacy_not_modified_proof_chain(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    """304은 과거 304 receipt가 아니라 마지막 authoritative receipt만 계승한다."""

    admin_id = await _seed_admin(session_factory)
    plan_id = uuid.uuid4()
    authoritative_receipt_id = uuid.uuid4()
    poisoned_receipt_id = uuid.uuid4()
    fresh_receipt_id = uuid.uuid4()
    authoritative_item_id = uuid.uuid4()
    poisoned_item_id = uuid.uuid4()
    feature_uuid = uuid.uuid4()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            curated_plan_id=plan_id,
            slug=f"conditional-proof-{plan_id}",
            title="conditional immutable proof",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=2,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()

        authoritative = KtmCurationImportReceipt(
            receipt_id=authoritative_receipt_id,
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint="a" * 64,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=2,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="refresh",
            requested_is_published=False,
        )
        db.add(authoritative)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=authoritative.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=authoritative_item_id,
                source_curation_item_revision=2,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        await db.flush()
        canonical_poi = CuratedPlanPoi(
            curated_plan_id=plan_id,
            day_index=1,
            sort_order="authoritative",
            feature_uuid=feature_uuid,
            feature_snapshot={},
            source_curation_import_receipt_id=authoritative.receipt_id,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_item_id=authoritative_item_id,
            source_curation_item_revision=2,
            source_curation_item_etag=_ETAG,
        )
        db.add(canonical_poi)
        await db.flush()
        authoritative.status = "completed"
        authoritative.result_plan_id = plan_id
        authoritative.response_status = 200
        authoritative.response_body = _terminal_response(authoritative, plan_id, created_plan=False)
        authoritative.completed_at = datetime.now(UTC)
        await db.commit()

    # 0055 이전 구현이 만들 수 있었던 poisoned 304 terminal: plan은 revision 2지만
    # 현재 POI는 revision 1 item으로 교체된 상태에서 304 proof를 다시 봉인했다.
    async with session_factory() as db:
        plan = await db.get(CuratedTripPlan, plan_id)
        canonical_poi = await db.scalar(
            select(CuratedPlanPoi).where(CuratedPlanPoi.curated_plan_id == plan_id)
        )
        assert plan is not None
        assert canonical_poi is not None
        poisoned = KtmCurationImportReceipt(
            receipt_id=poisoned_receipt_id,
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint="b" * 64,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=2,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="refresh",
            requested_is_published=False,
        )
        db.add(poisoned)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=poisoned.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=poisoned_item_id,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        await db.flush()
        canonical_poi.source_curation_import_receipt_id = poisoned.receipt_id
        canonical_poi.source_curation_item_id = poisoned_item_id
        canonical_poi.source_curation_item_revision = 1
        canonical_poi.source_curation_item_etag = _ETAG
        await db.flush()
        poisoned.status = "completed"
        poisoned.result_plan_id = plan_id
        poisoned.response_status = 200
        poisoned.response_body = _terminal_response(
            poisoned, plan_id, created_plan=False, not_modified=True
        )
        poisoned.completed_at = datetime.now(UTC)
        await db.commit()

    async with session_factory() as db:
        plan = await db.get(CuratedTripPlan, plan_id)
        assert plan is not None
        fresh = KtmCurationImportReceipt(
            receipt_id=fresh_receipt_id,
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint="d" * 64,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=2,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="refresh",
            requested_is_published=False,
        )
        db.add(fresh)
        await db.flush()
        with pytest.raises(
            CurationCollectionImportConflict,
            match="immutable conditional snapshot proof",
        ):
            await _apply_not_modified(
                db,
                receipt=fresh,
                plan=plan,
                source_etag=_ETAG,
            )
        assert (
            await db.scalar(
                select(KtmCurationImportReceiptItem).where(
                    KtmCurationImportReceiptItem.receipt_id == fresh_receipt_id
                )
            )
            is None
        )
        await db.rollback()


async def test_forward_only_downgrade_is_fail_closed(_database_url: str) -> None:
    """head부터의 downgrade는 가장 가까운 forward-only migration에서 멈춘다."""

    with pytest.raises(RuntimeError, match="forward-only"):
        _alembic(_database_url, "downgrade", "20260814_0058")


async def _seed_receipt_with_deleted_canonical_poi(
    session_factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:  # type: ignore[no-untyped-def]
    """active 1건과 soft-deleted canonical POI 1건을 가진 pending receipt를 만든다."""

    admin_id = await _seed_admin(session_factory)
    collection_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    supporting_receipt_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    deleted_poi_id = uuid.uuid4()
    active_item_id = uuid.uuid4()
    deleted_item_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            CuratedTripPlan(
                curated_plan_id=plan_id,
                slug=f"receipt-deleted-lock-{plan_id}",
                title="삭제 POI 락",
                category="recommended",
                source_system="kor-travel-map",
                source_curation_collection_id=collection_id,
                source_curation_collection_revision=1,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
            )
        )
        for current_receipt_id, current_key in (
            (receipt_id, uuid.uuid4()),
            (supporting_receipt_id, uuid.uuid4()),
        ):
            db.add(
                KtmCurationImportReceipt(
                    receipt_id=current_receipt_id,
                    actor_admin_id=admin_id,
                    idempotency_key=current_key,
                    request_fingerprint=_FINGERPRINT,
                    source_curation_collection_id=collection_id,
                    source_curation_collection_revision=1,
                    source_curation_collection_etag=_ETAG,
                    source_curation_item_set_hash_version="ktm-db-item-set-v1",
                    source_curation_item_set_hash=_ITEM_SET_HASH,
                    source_curation_item_count=1,
                    mode="refresh",
                    requested_is_published=False,
                )
            )
        await db.flush()
        active_feature_id = uuid.uuid4()
        deleted_feature_id = uuid.uuid4()
        db.add_all(
            [
                KtmCurationImportReceiptItem(
                    receipt_id=receipt_id,
                    source_curation_collection_id=collection_id,
                    source_curation_item_id=active_item_id,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                    feature_uuid=active_feature_id,
                ),
                KtmCurationImportReceiptItem(
                    receipt_id=supporting_receipt_id,
                    source_curation_collection_id=collection_id,
                    source_curation_item_id=deleted_item_id,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                    feature_uuid=deleted_feature_id,
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                CuratedPlanPoi(
                    curated_plan_id=plan_id,
                    day_index=1,
                    sort_order="a",
                    feature_uuid=active_feature_id,
                    feature_snapshot={},
                    source_curation_import_receipt_id=receipt_id,
                    source_curation_collection_id=collection_id,
                    source_curation_item_id=active_item_id,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                ),
                CuratedPlanPoi(
                    curated_poi_id=deleted_poi_id,
                    curated_plan_id=plan_id,
                    day_index=1,
                    sort_order="b",
                    feature_uuid=deleted_feature_id,
                    feature_snapshot={},
                    source_curation_import_receipt_id=supporting_receipt_id,
                    source_curation_collection_id=collection_id,
                    source_curation_item_id=deleted_item_id,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                    deleted_at=datetime.now(UTC),
                ),
            ]
        )
        await db.commit()
    return receipt_id, plan_id, deleted_poi_id


async def test_canonical_provenance_and_receipt_are_constrained_and_append_only(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _seed_admin(session_factory)
    idempotency_key = uuid.uuid4()

    async with session_factory() as db:
        feature_uuid = uuid.uuid4()
        plan = CuratedTripPlan(
            slug=f"map-{_COLLECTION_ID}",
            title="정본 컬렉션",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=7,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            source_imported_at=datetime.now(UTC),
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=idempotency_key,
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=7,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=3,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        # SQLAlchemy에는 이 composite FK의 relationship이 없으므로 receipt proof를
        # 먼저 영속화해 실제 importer가 지켜야 하는 insert 순서를 고정한다.
        await db.flush()
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=1,
                sort_order="a",
                feature_uuid=feature_uuid,
                feature_snapshot={},
                source_curation_import_receipt_id=receipt.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=3,
                source_curation_item_etag=_ETAG,
            )
        )
        manual_poi = CuratedPlanPoi(
            curated_plan_id=plan.curated_plan_id,
            day_index=1,
            sort_order="z",
            feature_uuid=uuid.uuid4(),
            feature_snapshot={"title": "수동 POI"},
        )
        db.add(manual_poi)
        await db.commit()
        plan_id = plan.curated_plan_id
        receipt_id = receipt.receipt_id
        manual_poi_id = manual_poi.curated_poi_id

    async with session_factory() as db:
        receipt = await db.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        receipt.status = "completed"
        receipt.result_plan_id = plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(receipt, plan_id, created_plan=True)
        receipt.completed_at = datetime.now(UTC)
        await db.commit()

    # 같은 Map ETag가 304를 반환한 fresh idempotency command는 receipt/proof만
    # 새로 보존한다. 기존 canonical POI의 originating receipt와 수동 PO이는 바꾸지 않는다.
    no_op_receipt_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            KtmCurationImportReceipt(
                receipt_id=no_op_receipt_id,
                actor_admin_id=admin_id,
                idempotency_key=uuid.uuid4(),
                request_fingerprint="d" * 64,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_collection_revision=7,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                mode="refresh",
                requested_is_published=False,
            )
        )
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=no_op_receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=3,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        await db.flush()
        no_op_receipt = await db.get(KtmCurationImportReceipt, no_op_receipt_id)
        assert no_op_receipt is not None
        no_op_receipt.status = "completed"
        no_op_receipt.result_plan_id = plan_id
        no_op_receipt.response_status = 200
        no_op_receipt.response_body = _terminal_response(
            no_op_receipt, plan_id, created_plan=False, not_modified=True
        )
        no_op_receipt.completed_at = datetime.now(UTC)
        await db.commit()

    async with session_factory() as db:
        pois = (
            await db.scalars(
                select(CuratedPlanPoi)
                .where(CuratedPlanPoi.curated_plan_id == plan_id)
                .order_by(CuratedPlanPoi.sort_order)
            )
        ).all()
        assert len(pois) == 2
        canonical_poi = next(poi for poi in pois if poi.source_curation_item_id is not None)
        assert canonical_poi.source_curation_import_receipt_id == receipt_id
        assert next(
            poi for poi in pois if poi.curated_poi_id == manual_poi_id
        ).feature_snapshot == {"title": "수동 POI"}
        no_op_receipt = await db.get(KtmCurationImportReceipt, no_op_receipt_id)
        assert no_op_receipt is not None
        assert no_op_receipt.status == "completed"

    async with session_factory() as db:
        db.add(
            KtmCurationImportReceipt(
                actor_admin_id=admin_id,
                idempotency_key=idempotency_key,
                request_fingerprint=_FINGERPRINT,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_collection_revision=7,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                mode="create",
                requested_is_published=False,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
    async with session_factory() as db:
        native_plan = CuratedTripPlan(
            slug="native-plan",
            title="수동 plan",
            category="recommended",
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(native_plan)
        await db.flush()
        db.add(
            CuratedPlanPoi(
                curated_plan_id=native_plan.curated_plan_id,
                day_index=1,
                sort_order="a",
                feature_uuid=uuid.uuid4(),
                feature_snapshot={},
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        db.add(
            KtmCurationImportReceipt(
                actor_admin_id=admin_id,
                idempotency_key=uuid.uuid4(),
                request_fingerprint=_FINGERPRINT,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_collection_revision=7,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                mode="refresh",
                requested_is_published=False,
                status="completed",
                result_plan_id=plan_id,
                response_status=200,
                response_body={
                    "notice_plan_id": str(plan_id),
                    "source_curation_collection_id": str(_COLLECTION_ID),
                },
                completed_at=datetime.now(UTC),
            )
        )
        with pytest.raises(DBAPIError, match="must start pending"):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        receipt = await db.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        receipt.response_status = 200
        with pytest.raises(DBAPIError, match="immutable"):
            await db.commit()
        await db.rollback()

        receipt = await db.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        await db.delete(receipt)
        with pytest.raises(DBAPIError, match="append-only"):
            await db.commit()


async def test_receipt_completion_serializes_member_insert(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _seed_admin(session_factory)
    receipt_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    feature_uuid = uuid.uuid4()

    async with session_factory() as db:
        db.add(
            CuratedTripPlan(
                curated_plan_id=plan_id,
                slug=f"receipt-lock-{plan_id}",
                title="영수증 락",
                category="recommended",
                source_system="kor-travel-map",
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_collection_revision=1,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
            )
        )
        db.add(
            KtmCurationImportReceipt(
                receipt_id=receipt_id,
                actor_admin_id=admin_id,
                idempotency_key=uuid.uuid4(),
                request_fingerprint=_FINGERPRINT,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_collection_revision=1,
                source_curation_collection_etag=_ETAG,
                source_curation_item_set_hash_version="ktm-db-item-set-v1",
                source_curation_item_set_hash=_ITEM_SET_HASH,
                source_curation_item_count=1,
                mode="create",
                requested_is_published=False,
            )
        )
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        await db.flush()
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan_id,
                day_index=1,
                sort_order="a",
                feature_uuid=feature_uuid,
                feature_snapshot={},
                source_curation_import_receipt_id=receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
            )
        )
        await db.commit()

    started = asyncio.Event()

    async def _insert_late_member() -> str:
        async with session_factory() as db:
            started.set()
            try:
                await db.execute(
                    text(
                        "INSERT INTO app.ktm_curation_import_receipt_items ("
                        "receipt_id, source_curation_collection_id, "
                        "source_curation_item_id, source_curation_item_revision, "
                        "source_curation_item_etag, feature_uuid) VALUES ("
                        ":receipt_id, :collection_id, :item_id, 1, :etag, :feature_uuid)"
                    ),
                    {
                        "receipt_id": receipt_id,
                        "collection_id": _COLLECTION_ID,
                        "item_id": uuid.uuid4(),
                        "etag": _ETAG,
                        "feature_uuid": uuid.uuid4(),
                    },
                )
                await db.commit()
            except DBAPIError as exc:
                await db.rollback()
                return str(exc)
        return "unexpected success"

    async with session_factory() as completing:
        receipt = await completing.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        receipt.status = "completed"
        receipt.result_plan_id = plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(receipt, plan_id, created_plan=True)
        receipt.completed_at = datetime.now(UTC)
        await completing.flush()

        late_insert = asyncio.create_task(_insert_late_member())
        await started.wait()
        await asyncio.sleep(0.1)
        assert not late_insert.done()
        await completing.commit()

    error = await asyncio.wait_for(late_insert, timeout=5)
    assert "requires pending receipt" in error
    async with session_factory() as db:
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM app.ktm_curation_import_receipt_items "
                    "WHERE receipt_id = :receipt_id"
                ),
                {"receipt_id": receipt_id},
            )
            == 1
        )


async def test_receipt_completion_serializes_deleted_canonical_poi_reactivation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    """soft-deleted canonical POI도 terminal exact-set lock에 포함한다."""

    receipt_id, plan_id, deleted_poi_id = await _seed_receipt_with_deleted_canonical_poi(
        session_factory
    )
    writer_started = asyncio.Event()

    async def _reactivate_deleted_poi() -> str:
        async with session_factory() as db:
            writer_started.set()
            await db.execute(
                text(
                    "UPDATE app.curated_plan_pois SET deleted_at = NULL "
                    "WHERE curated_poi_id = :poi_id"
                ),
                {"poi_id": deleted_poi_id},
            )
            await db.commit()
        return "updated"

    # Completer가 먼저 exact set을 seal하면 undelete는 commit까지 기다린다.
    async with session_factory() as completing:
        receipt = await completing.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        receipt.status = "completed"
        receipt.result_plan_id = plan_id
        receipt.response_status = 200
        receipt.response_body = _terminal_response(receipt, plan_id, created_plan=False)
        receipt.completed_at = datetime.now(UTC)
        await completing.flush()

        writer = asyncio.create_task(_reactivate_deleted_poi())
        await writer_started.wait()
        await asyncio.sleep(0.1)
        assert not writer.done()
        await completing.commit()
    assert await asyncio.wait_for(writer, timeout=5) == "updated"

    # Writer-first interleaving은 completion이 기다린 뒤 변경된 active set을 다시 읽어
    # pending receipt를 terminal로 만들지 않는다.
    (
        second_receipt_id,
        second_plan_id,
        second_deleted_poi_id,
    ) = await _seed_receipt_with_deleted_canonical_poi(session_factory)
    writer_holds_row = asyncio.Event()
    release_writer = asyncio.Event()

    async def _reactivate_and_hold() -> None:
        async with session_factory() as db:
            await db.execute(
                text(
                    "UPDATE app.curated_plan_pois SET deleted_at = NULL "
                    "WHERE curated_poi_id = :poi_id"
                ),
                {"poi_id": second_deleted_poi_id},
            )
            writer_holds_row.set()
            await release_writer.wait()
            await db.commit()

    async def _complete_after_writer() -> str:
        async with session_factory() as db:
            receipt = await db.get(KtmCurationImportReceipt, second_receipt_id)
            assert receipt is not None
            receipt.status = "completed"
            receipt.result_plan_id = second_plan_id
            receipt.response_status = 200
            receipt.response_body = _terminal_response(receipt, second_plan_id, created_plan=False)
            receipt.completed_at = datetime.now(UTC)
            try:
                await db.commit()
            except DBAPIError as exc:
                await db.rollback()
                return str(exc)
        return "unexpected success"

    holding_writer = asyncio.create_task(_reactivate_and_hold())
    await writer_holds_row.wait()
    completion = asyncio.create_task(_complete_after_writer())
    await asyncio.sleep(0.1)
    assert not completion.done()
    release_writer.set()
    await asyncio.wait_for(holding_writer, timeout=5)
    error = await asyncio.wait_for(completion, timeout=5)
    assert "POI set does not match" in error
    async with session_factory() as db:
        second_receipt = await db.get(KtmCurationImportReceipt, second_receipt_id)
        assert second_receipt is not None
        assert second_receipt.status == "pending"


async def test_partial_or_duplicate_canonical_provenance_is_rejected(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _seed_admin(session_factory)

    async with session_factory() as db:
        db.add(
            CuratedTripPlan(
                slug="partial-map-source",
                title="불완전 provenance",
                category="recommended",
                source_system="kor-travel-map",
                source_curation_collection_id=_COLLECTION_ID,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_terminal_receipt_is_bound_to_source_plan_body_and_item_set(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _seed_admin(session_factory)

    async with session_factory() as db:
        native_plan = CuratedTripPlan(
            slug="unrelated-native-plan",
            title="무관 plan",
            category="recommended",
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(native_plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=0,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        receipt.status = "completed"
        receipt.result_plan_id = native_plan.curated_plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(
            receipt, native_plan.curated_plan_id, created_plan=True
        )
        receipt.completed_at = datetime.now(UTC)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="canonical-plan-for-tuple-mismatch",
            title="정본 tuple 불일치 plan",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=0,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=2,
            source_curation_collection_etag='"sha256:' + ("d" * 64) + '"',
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash="e" * 64,
            source_curation_item_count=0,
            mode="refresh",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        receipt.status = "completed"
        receipt.result_plan_id = plan.curated_plan_id
        receipt.response_status = 200
        receipt.response_body = _terminal_response(
            receipt, plan.curated_plan_id, created_plan=False
        )
        receipt.completed_at = datetime.now(UTC)
        with pytest.raises(DBAPIError, match="result plan proof does not match"):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="canonical-plan-for-receipt",
            title="정본 plan",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        receipt.status = "completed"
        receipt.result_plan_id = plan.curated_plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(receipt, plan.curated_plan_id, created_plan=True)
        receipt.completed_at = datetime.now(UTC)
        with pytest.raises(DBAPIError, match="item set is incomplete"):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="canonical-plan-for-missing-poi",
            title="POI 누락 plan",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
                feature_uuid=uuid.uuid4(),
            )
        )
        await db.flush()
        receipt.status = "completed"
        receipt.result_plan_id = plan.curated_plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(receipt, plan.curated_plan_id, created_plan=True)
        receipt.completed_at = datetime.now(UTC)
        with pytest.raises(DBAPIError, match="POI set does not match"):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="canonical-plan-for-body",
            title="정본 body plan",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=0,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=0,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        receipt.status = "completed"
        receipt.result_plan_id = plan.curated_plan_id
        receipt.response_status = 201
        receipt.response_body = _terminal_response(receipt, plan.curated_plan_id, created_plan=True)
        receipt.response_body["notice_plan_id"] = str(uuid.uuid4())
        receipt.completed_at = datetime.now(UTC)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="duplicate-item-source",
            title="중복 item provenance",
            category="recommended",
            source_system="kor-travel-map",
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        feature_uuid = uuid.uuid4()
        receipt = KtmCurationImportReceipt(
            actor_admin_id=admin_id,
            idempotency_key=uuid.uuid4(),
            request_fingerprint=_FINGERPRINT,
            source_curation_collection_id=_COLLECTION_ID,
            source_curation_collection_revision=1,
            source_curation_collection_etag=_ETAG,
            source_curation_item_set_hash_version="ktm-db-item-set-v1",
            source_curation_item_set_hash=_ITEM_SET_HASH,
            source_curation_item_count=1,
            mode="create",
            requested_is_published=False,
        )
        db.add(receipt)
        await db.flush()
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt.receipt_id,
                source_curation_collection_id=_COLLECTION_ID,
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=1,
                source_curation_item_etag=_ETAG,
                feature_uuid=feature_uuid,
            )
        )
        for sort_order in ("a", "b"):
            db.add(
                CuratedPlanPoi(
                    curated_plan_id=plan.curated_plan_id,
                    day_index=1,
                    sort_order=sort_order,
                    feature_uuid=feature_uuid,
                    feature_snapshot={},
                    source_curation_import_receipt_id=receipt.receipt_id,
                    source_curation_collection_id=_COLLECTION_ID,
                    source_curation_item_id=_ITEM_ID,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                )
            )
        with pytest.raises(IntegrityError):
            await db.commit()
