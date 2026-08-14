"""T-VN-40 canonical collection provenance와 import receipt를 실제 DB에서 검증한다."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationImportReceipt,
)
from app.models.user import User

pytestmark = pytest.mark.asyncio

_API_DIR = Path(__file__).resolve().parents[2]

_COLLECTION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ITEM_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_ETAG = '"sha256:' + ("a" * 64) + '"'
_ITEM_SET_HASH = "b" * 64
_FINGERPRINT = "c" * 64


def test_tvn40_curation_receipt_head_has_no_orm_metadata_drift(
    _database_url: str,
) -> None:
    env = dict(os.environ)
    env["PINVI_DATABASE_URL"] = _database_url
    result = subprocess.run(
        ["alembic", "check"],  # noqa: S607 -- repository venv의 고정 CLI
        cwd=_API_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=1,
                sort_order="a",
                feature_uuid=uuid.uuid4(),
                feature_snapshot={},
                source_curation_item_id=_ITEM_ID,
                source_curation_item_revision=3,
                source_curation_item_etag=_ETAG,
            )
        )
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
        await db.rollback()

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug="duplicate-item-source",
            title="중복 item provenance",
            category="recommended",
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
        )
        db.add(plan)
        await db.flush()
        for sort_order in ("a", "b"):
            db.add(
                CuratedPlanPoi(
                    curated_plan_id=plan.curated_plan_id,
                    day_index=1,
                    sort_order=sort_order,
                    feature_snapshot={},
                    source_curation_item_id=_ITEM_ID,
                    source_curation_item_revision=1,
                    source_curation_item_etag=_ETAG,
                )
            )
        with pytest.raises(IntegrityError):
            await db.commit()
