"""T-VN-40 canonical collection provenance와 import receipt를 실제 DB에서 검증한다."""

from __future__ import annotations

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
    KtmCurationImportReceipt,
    KtmCurationImportReceiptItem,
)
from app.models.user import User

pytestmark = pytest.mark.asyncio

API_DIR = Path(__file__).resolve().parents[2]
_COLLECTION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ITEM_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_ETAG = '"sha256:' + ("a" * 64) + '"'
_ITEM_SET_HASH = "b" * 64
_FINGERPRINT = "c" * 64


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


async def _assert_0052_catalog_contract(db: AsyncSession) -> None:
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
    assert "schema_revision = '20260814_0052'::text" in boundary_definition

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


async def test_tvn40_curation_receipt_catalog_is_exact_and_detects_semantic_drift(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        await _assert_0052_catalog_contract(db)
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
            await _assert_0052_catalog_contract(db)
        await db.rollback()


async def test_existing_0051_schema_and_data_upgrade_forward_to_0052(
    _database_url: str,
) -> None:
    _alembic(_database_url, "downgrade", "20260814_0051")
    try:
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
                        "idempotency_key": uuid.uuid4(),
                        "fingerprint": _FINGERPRINT,
                        "collection_id": _COLLECTION_ID,
                        "etag": _ETAG,
                        "item_hash": _ITEM_SET_HASH,
                        "plan_id": plan_id,
                        "response_body": json.dumps(
                            {
                                "notice_plan_id": str(plan_id),
                                "source_curation_collection_id": str(_COLLECTION_ID),
                            }
                        ),
                    },
                )
        finally:
            await engine.dispose()

        _alembic(_database_url, "upgrade", "20260814_0052")
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
                assert (await db.scalars(select(CuratedPlanPoi))).all() == []
        finally:
            await engine.dispose()
    finally:
        _alembic(_database_url, "upgrade", "head")


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
        await db.commit()
        plan_id = plan.curated_plan_id
        receipt_id = receipt.receipt_id

    async with session_factory() as db:
        receipt = await db.get(KtmCurationImportReceipt, receipt_id)
        assert receipt is not None
        receipt.status = "completed"
        receipt.result_plan_id = plan_id
        receipt.response_status = 201
        receipt.response_body = {
            "notice_plan_id": str(plan_id),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
        receipt.completed_at = datetime.now(UTC)
        await db.commit()

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
        await db.rollback()

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
        receipt.response_body = {
            "notice_plan_id": str(native_plan.curated_plan_id),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
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
        receipt.response_body = {
            "notice_plan_id": str(plan.curated_plan_id),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
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
        receipt.response_body = {
            "notice_plan_id": str(plan.curated_plan_id),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
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
        receipt.response_body = {
            "notice_plan_id": str(plan.curated_plan_id),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
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
        receipt.response_body = {
            "notice_plan_id": str(uuid.uuid4()),
            "source_curation_collection_id": str(_COLLECTION_ID),
        }
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
