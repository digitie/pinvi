"""T-VN-40C legacy plan→canonical collection typed backfill의 실제 DB 검증."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_curation import (
    CurationCollectionFetchResult,
    CurationCollectionSnapshotSet,
    CurationItemDetailSnapshot,
)
from app.core.config import KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationCutoverBackfillReceipt,
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
    KtmCurationImportReceipt,
    KtmCurationImportReceiptItem,
)
from app.models.user import User
from app.services.curation_cutover_backfill import (
    CurationCutoverBackfillConflict,
    apply_curation_cutover_backfill,
)

pytestmark = pytest.mark.asyncio

_ROOT = "a" * 64
_ROW_HASH = "b" * 64
_COLLECTION_ETAG = '"sha256:' + ("c" * 64) + '"'


async def _admin(db: AsyncSession) -> User:
    admin = User(
        email=f"cutover-backfill-{uuid.uuid4().hex}@pinvi.test",
        password_hash="x",
        nickname="cutover backfill",
        status="active",
        roles=["user", "admin"],
        email_verified_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.flush()
    return admin


async def _sealed_mapping(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    legacy_id: uuid.UUID,
    collection_id: uuid.UUID,
    curation_item_id: uuid.UUID,
) -> KtmCurationCutoverMappingReceipt:
    receipt = KtmCurationCutoverMappingReceipt(
        actor_admin_id=admin_id,
        map_release_revision=KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        mapping_root_version="ktm-curation-cutover-mapping-v1",
        mapping_root=_ROOT,
        mapping_count=1,
    )
    db.add(receipt)
    await db.flush()
    db.add(
        KtmCurationCutoverMappingReceiptItem(
            receipt_id=receipt.receipt_id,
            legacy_curated_feature_id=legacy_id,
            collection_id=collection_id,
            curation_item_id=curation_item_id,
            mapping_kind="legacy_projection",
            source_row_hash=_ROW_HASH,
        )
    )
    await db.flush()
    receipt.status = "completed"
    receipt.completed_at = datetime.now(UTC)
    await db.flush()
    return receipt


def _snapshot(
    *,
    collection_id: uuid.UUID,
    curation_item_id: uuid.UUID,
) -> CurationCollectionFetchResult:
    feature_id = uuid.uuid4()
    item = CurationItemDetailSnapshot.model_validate(
        {
            "curation_item_id": str(curation_item_id),
            "collection_id": str(collection_id),
            "row_revision": "1",
            "etag": "sha256:" + ("d" * 64),
            "updated_at": "2026-08-14T00:00:00Z",
            "collection": {
                "theme_slug": "cafes",
                "theme_name": "카페",
                "title": "서울 카페",
                "edition_key": "2026",
            },
            "item": {
                "feature_id": str(feature_id),
                "relation": "food_stop",
                "sort_order": 1,
                "title": "카페",
                "summary": "canonical memo",
            },
            "feature": {
                "feature_id": str(feature_id),
                "name": "canonical 카페",
                "category": "food",
                "kind": "place",
                "lon": 126.9,
                "lat": 37.5,
                "address": {"road_address": "서울"},
                "detail": {},
                "source_record_key": "source:canonical",
            },
        }
    )
    return CurationCollectionFetchResult(
        not_modified=False,
        source_etag=_COLLECTION_ETAG,
        snapshot=CurationCollectionSnapshotSet(
            collection_id=collection_id,
            row_revision=1,
            source_etag=_COLLECTION_ETAG,
            updated_at=datetime(2026, 8, 14, tzinfo=UTC),
            collection=item.collection,
            item_count=1,
            item_set_hash_version="ktm-db-item-set-v1",
            item_set_hash="e" * 64,
            items=(item,),
        ),
    )


class _FakeSnapshotClient:
    def __init__(self, result: CurationCollectionFetchResult) -> None:
        self.result = result
        self.calls: list[tuple[uuid.UUID, str | None]] = []

    async def get_collection_snapshot(
        self,
        collection_id: uuid.UUID,
        *,
        if_none_match: str | None = None,
    ) -> CurationCollectionFetchResult:
        self.calls.append((collection_id, if_none_match))
        return self.result


async def test_cutover_backfill_promotes_exact_mapping_and_preserves_manual_poi(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    legacy_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    curation_item_id = uuid.uuid4()
    command_key = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        mapping_receipt = await _sealed_mapping(
            db,
            admin_id=admin.user_id,
            legacy_id=legacy_id,
            collection_id=collection_id,
            curation_item_id=curation_item_id,
        )
        plan = CuratedTripPlan(
            slug=f"legacy-{legacy_id}",
            title="legacy title",
            category="recommended",
            source_system="kor-travel-map",
            source_curated_feature_id=str(legacy_id),
            is_published=True,
            created_by_admin_id=admin.user_id,
            updated_by_admin_id=admin.user_id,
        )
        db.add(plan)
        await db.flush()
        legacy_poi = CuratedPlanPoi(
            curated_plan_id=plan.curated_plan_id,
            day_index=1,
            sort_order="legacy",
            feature_snapshot={},
            source_curated_feature_id=str(legacy_id),
            source_curated_feature_item_id="legacy-item-1",
        )
        manual_poi = CuratedPlanPoi(
            curated_plan_id=plan.curated_plan_id,
            day_index=1,
            sort_order="manual",
            feature_snapshot={},
        )
        db.add_all([legacy_poi, manual_poi])
        await db.commit()
        admin_id = admin.user_id
        plan_id = plan.curated_plan_id
        legacy_poi_id = legacy_poi.curated_poi_id
        manual_poi_id = manual_poi.curated_poi_id
        mapping_receipt_id = mapping_receipt.receipt_id

    fetched = _snapshot(collection_id=collection_id, curation_item_id=curation_item_id)
    async with session_factory() as db:
        result = await apply_curation_cutover_backfill(
            db,
            actor_admin_id=admin_id,
            idempotency_key=command_key,
            curated_plan_id=plan_id,
            fetched=fetched,
        )
        assert result.replayed is False
        assert result.import_result.status_code == 201
        assert result.import_result.response.notice_plan_id == plan_id
        assert result.import_result.response.created_plan is False
        assert result.import_result.response.copied_poi_count == 1
        assert result.import_result.response.removed_poi_count == 1
        await db.commit()

    async with session_factory() as db:
        plan = await db.get(CuratedTripPlan, plan_id)
        legacy_poi = await db.get(CuratedPlanPoi, legacy_poi_id)
        manual_poi = await db.get(CuratedPlanPoi, manual_poi_id)
        backfill_receipt = await db.scalar(
            select(KtmCurationCutoverBackfillReceipt).where(
                KtmCurationCutoverBackfillReceipt.curated_plan_id == plan_id
            )
        )
        assert plan is not None
        assert legacy_poi is not None
        assert manual_poi is not None
        assert backfill_receipt is not None
        assert plan.source_curated_feature_id == str(legacy_id)
        assert plan.source_curation_collection_id == collection_id
        assert plan.source_curation_collection_etag == _COLLECTION_ETAG
        assert plan.is_published is True
        assert legacy_poi.deleted_at is not None
        assert manual_poi.deleted_at is None
        assert backfill_receipt.mapping_receipt_id == mapping_receipt_id
        assert backfill_receipt.status == "completed"
        assert backfill_receipt.import_receipt_id is not None
        import_receipt = await db.get(KtmCurationImportReceipt, backfill_receipt.import_receipt_id)
        assert import_receipt is not None
        assert import_receipt.mode == "cutover-backfill"
        assert import_receipt.status == "completed"
        assert (
            await db.scalar(
                select(func.count(KtmCurationImportReceiptItem.receipt_id)).where(
                    KtmCurationImportReceiptItem.receipt_id == import_receipt.receipt_id
                )
            )
            == 1
        )
        canonical_pois = (
            await db.scalars(
                select(CuratedPlanPoi).where(
                    CuratedPlanPoi.curated_plan_id == plan_id,
                    CuratedPlanPoi.deleted_at.is_(None),
                    CuratedPlanPoi.source_curation_item_id.is_not(None),
                )
            )
        ).all()
        assert [poi.source_curation_item_id for poi in canonical_pois] == [curation_item_id]

    async with session_factory() as db:
        replay = await apply_curation_cutover_backfill(
            db,
            actor_admin_id=admin_id,
            idempotency_key=command_key,
            curated_plan_id=plan_id,
            fetched=fetched,
        )
        assert replay.replayed is True
        assert replay.import_result.status_code == 201
        await db.rollback()


async def test_cutover_backfill_rejects_snapshot_outside_sealed_mapping(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    legacy_id = uuid.uuid4()
    mapped_collection_id = uuid.uuid4()
    curation_item_id = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        await _sealed_mapping(
            db,
            admin_id=admin.user_id,
            legacy_id=legacy_id,
            collection_id=mapped_collection_id,
            curation_item_id=curation_item_id,
        )
        plan = CuratedTripPlan(
            slug=f"legacy-conflict-{legacy_id}",
            title="legacy conflict",
            category="recommended",
            source_system="kor-travel-map",
            source_curated_feature_id=str(legacy_id),
            created_by_admin_id=admin.user_id,
            updated_by_admin_id=admin.user_id,
        )
        db.add(plan)
        await db.commit()
        admin_id = admin.user_id
        plan_id = plan.curated_plan_id

    async with session_factory() as db:
        with pytest.raises(CurationCutoverBackfillConflict, match="remote canonical snapshot"):
            await apply_curation_cutover_backfill(
                db,
                actor_admin_id=admin_id,
                idempotency_key=uuid.uuid4(),
                curated_plan_id=plan_id,
                fetched=_snapshot(
                    collection_id=uuid.uuid4(),
                    curation_item_id=curation_item_id,
                ),
            )
        await db.rollback()


async def test_admin_cutover_backfill_fetches_sealed_collection_and_replays(
    client,
    session_factory,
    auth_cookies,
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import get_curation_snapshot_service_client
    from app.main import app
    from app.models.audit import AdminAuditLog

    legacy_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    curation_item_id = uuid.uuid4()
    command_key = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        mapping_receipt = await _sealed_mapping(
            db,
            admin_id=admin.user_id,
            legacy_id=legacy_id,
            collection_id=collection_id,
            curation_item_id=curation_item_id,
        )
        plan = CuratedTripPlan(
            slug=f"legacy-route-{legacy_id}",
            title="legacy route title",
            category="recommended",
            source_system="kor-travel-map",
            source_curated_feature_id=str(legacy_id),
            created_by_admin_id=admin.user_id,
            updated_by_admin_id=admin.user_id,
        )
        db.add(plan)
        await db.flush()
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=1,
                sort_order="legacy-route",
                feature_snapshot={},
                source_curated_feature_id=str(legacy_id),
                source_curated_feature_item_id="legacy-route-item",
            )
        )
        await db.commit()
        admin_id = admin.user_id
        plan_id = plan.curated_plan_id
        mapping_receipt_id = mapping_receipt.receipt_id

    fake = _FakeSnapshotClient(
        _snapshot(collection_id=collection_id, curation_item_id=curation_item_id)
    )
    app.dependency_overrides[get_curation_snapshot_service_client] = lambda: fake
    try:
        created = await client.post(
            "/admin/notice-plans/curation-cutover/backfills",
            json={"notice_plan_id": str(plan_id)},
            headers={"Idempotency-Key": str(command_key)},
            cookies=auth_cookies(str(admin_id)),
        )
        assert created.status_code == 201, created.text
        created_data = created.json()["data"]
        assert created_data["replayed"] is False
        assert created_data["mapping_receipt_id"] == str(mapping_receipt_id)
        assert created_data["legacy_curated_feature_id"] == str(legacy_id)
        assert created_data["import_result"]["notice_plan_id"] == str(plan_id)
        assert created_data["import_result"]["created_plan"] is False
        assert fake.calls == [(collection_id, None)]

        replay = await client.post(
            "/admin/notice-plans/curation-cutover/backfills",
            json={"notice_plan_id": str(plan_id)},
            headers={"Idempotency-Key": str(command_key)},
            cookies=auth_cookies(str(admin_id)),
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"] == {**created_data, "replayed": True}
        assert fake.calls == [(collection_id, None)]

        async with session_factory() as db:
            assert (
                await db.scalar(select(func.count(KtmCurationCutoverBackfillReceipt.receipt_id)))
                == 1
            )
            assert await db.scalar(select(func.count(AdminAuditLog.log_id))) == 1
    finally:
        app.dependency_overrides.pop(get_curation_snapshot_service_client, None)
