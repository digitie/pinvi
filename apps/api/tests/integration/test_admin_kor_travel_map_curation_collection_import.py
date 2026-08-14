"""Map canonical collection → PinVi plan atomic import 통합 테스트."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio

COLLECTION_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
ETAG_1 = '"sha256:' + ("a" * 64) + '"'
ETAG_2 = '"sha256:' + ("b" * 64) + '"'


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"canonical_import_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="관리자",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        return str(user.user_id)


def _item(number: int, *, revision: int = 1):  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import CurationItemDetailSnapshot

    item_id = uuid.UUID(f"20000000-0000-0000-0000-{number:012d}")
    feature_id = uuid.UUID(f"30000000-0000-0000-0000-{number:012d}")
    return CurationItemDetailSnapshot.model_validate(
        {
            "curation_item_id": str(item_id),
            "collection_id": str(COLLECTION_ID),
            "row_revision": str(revision),
            "etag": f"sha256:{number + revision:064x}",
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
                "sort_order": number,
                "title": None,
                "summary": f"메모 {number}",
            },
            "feature": {
                "feature_id": str(feature_id),
                "name": f"카페 {number}",
                "category": "food",
                "kind": "place",
                "lon": 126.9,
                "lat": 37.5,
                "address": {"road_address": "서울"},
                "detail": {},
                "source_record_key": f"source:{number}",
            },
        }
    )


def _snapshot(*, revision: int, etag: str, item_numbers: tuple[int, ...]):  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import CurationCollectionSnapshotSet

    return CurationCollectionSnapshotSet(
        collection_id=COLLECTION_ID,
        row_revision=revision,
        source_etag=etag,
        updated_at=datetime(2026, 8, 14, tzinfo=UTC),
        collection=_item(1).collection,
        item_count=len(item_numbers),
        item_set_hash_version="ktm-db-item-set-v1",
        item_set_hash=("c" if revision == 1 else "d") * 64,
        items=tuple(_item(number, revision=revision) for number in item_numbers),
    )


class _FakeSnapshotClient:
    def __init__(self, results) -> None:  # type: ignore[no-untyped-def]
        self.results = list(results)
        self.calls: list[tuple[uuid.UUID, str | None]] = []

    async def get_collection_snapshot(
        self, collection_id: uuid.UUID, *, if_none_match: str | None = None
    ):  # type: ignore[no-untyped-def]
        self.calls.append((collection_id, if_none_match))
        return self.results.pop(0)


class _ConcurrentSnapshotClient:
    def __init__(self, result) -> None:  # type: ignore[no-untyped-def]
        self.result = result
        self.calls = 0
        self.ready = asyncio.Event()

    async def get_collection_snapshot(
        self, _collection_id: uuid.UUID, *, if_none_match: str | None = None
    ):  # type: ignore[no-untyped-def]
        assert if_none_match is None
        self.calls += 1
        if self.calls == 2:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        return self.result


async def test_canonical_collection_import_replay_refresh_and_manual_poi_preservation(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import (
        CurationCollectionFetchResult,
        get_curation_snapshot_service_client,
    )
    from app.main import app
    from app.models.audit import AdminAuditLog
    from app.models.curated_plan import (
        CuratedPlanPoi,
        CuratedTripPlan,
        KtmCurationImportReceipt,
        KtmCurationImportReceiptItem,
    )

    admin_id = await _admin(session_factory)
    fake = _FakeSnapshotClient(
        [
            CurationCollectionFetchResult(
                not_modified=False,
                source_etag=ETAG_1,
                snapshot=_snapshot(revision=1, etag=ETAG_1, item_numbers=(1, 2)),
            ),
            CurationCollectionFetchResult(
                not_modified=True,
                source_etag=ETAG_1,
                snapshot=None,
            ),
            CurationCollectionFetchResult(
                not_modified=False,
                source_etag=ETAG_2,
                snapshot=_snapshot(revision=2, etag=ETAG_2, item_numbers=(2, 3)),
            ),
        ]
    )
    app.dependency_overrides[get_curation_snapshot_service_client] = lambda: fake
    create_key = uuid.uuid4()
    try:
        created = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={
                "collection_id": str(COLLECTION_ID),
                "mode": "create",
                "is_published": True,
            },
            headers={"Idempotency-Key": str(create_key)},
            cookies=auth_cookies(admin_id),
        )
        assert created.status_code == 201, created.text
        created_data = created.json()["data"]
        assert created_data["created_plan"] is True
        assert created_data["not_modified"] is False
        assert created_data["copied_poi_count"] == 2
        plan_id = uuid.UUID(created_data["notice_plan_id"])

        replay = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={
                "collection_id": str(COLLECTION_ID),
                "mode": "create",
                "is_published": True,
            },
            headers={"Idempotency-Key": str(create_key)},
            cookies=auth_cookies(admin_id),
        )
        assert replay.status_code == 201
        assert replay.json() == created.json()
        assert len(fake.calls) == 1

        conflict = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={
                "collection_id": str(COLLECTION_ID),
                "mode": "create",
                "is_published": False,
            },
            headers={"Idempotency-Key": str(create_key)},
            cookies=auth_cookies(admin_id),
        )
        assert conflict.status_code == 409
        assert len(fake.calls) == 1

        async with session_factory() as db:
            plan = await db.get(CuratedTripPlan, plan_id)
            assert plan is not None
            initial_plan_version = plan.version
            pois = (
                await db.scalars(
                    select(CuratedPlanPoi).where(
                        CuratedPlanPoi.curated_plan_id == plan_id,
                        CuratedPlanPoi.deleted_at.is_(None),
                    )
                )
            ).all()
            initial_poi_versions = {poi.curated_poi_id: poi.version for poi in pois}
            manual = CuratedPlanPoi(
                curated_plan_id=plan_id,
                day_index=1,
                sort_order="manual",
                feature_snapshot={},
            )
            db.add(manual)
            await db.commit()
            manual_id = manual.curated_poi_id

        not_modified = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={"collection_id": str(COLLECTION_ID), "mode": "refresh"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
            cookies=auth_cookies(admin_id),
        )
        assert not_modified.status_code == 200, not_modified.text
        assert not_modified.json()["data"]["not_modified"] is True
        assert fake.calls[1] == (COLLECTION_ID, ETAG_1)

        refreshed = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={"collection_id": str(COLLECTION_ID), "mode": "refresh"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
            cookies=auth_cookies(admin_id),
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["data"]["copied_poi_count"] == 2
        assert refreshed.json()["data"]["removed_poi_count"] == 1
        assert fake.calls[2] == (COLLECTION_ID, ETAG_1)

        async with session_factory() as db:
            plan = await db.get(CuratedTripPlan, plan_id)
            assert plan is not None
            assert plan.version == initial_plan_version + 1
            assert plan.source_curation_collection_revision == 2
            assert plan.source_curation_collection_etag == ETAG_2
            all_pois = (
                await db.scalars(
                    select(CuratedPlanPoi).where(CuratedPlanPoi.curated_plan_id == plan_id)
                )
            ).all()
            manual = next(poi for poi in all_pois if poi.curated_poi_id == manual_id)
            assert manual.deleted_at is None
            canonical = {
                poi.source_curation_item_id: poi
                for poi in all_pois
                if poi.source_curation_item_id is not None
            }
            assert canonical[uuid.UUID("20000000-0000-0000-0000-000000000001")].deleted_at
            assert canonical[uuid.UUID("20000000-0000-0000-0000-000000000002")].deleted_at is None
            assert canonical[uuid.UUID("20000000-0000-0000-0000-000000000003")].deleted_at is None
            unchanged_versions = {
                poi.curated_poi_id: poi.version
                for poi in all_pois
                if poi.curated_poi_id in initial_poi_versions
            }
            assert all(
                unchanged_versions[poi_id] == version + 1
                for poi_id, version in initial_poi_versions.items()
            )
            assert await db.scalar(select(func.count(KtmCurationImportReceipt.receipt_id))) == 3
            assert (
                await db.scalar(select(func.count(KtmCurationImportReceiptItem.receipt_id)))
                == 6
            )
            assert await db.scalar(select(func.count(AdminAuditLog.log_id))) == 2
    finally:
        app.dependency_overrides.pop(get_curation_snapshot_service_client, None)


async def test_canonical_collection_import_audit_failure_rolls_back_everything(
    client, session_factory, auth_cookies, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.api.v1.admin import notice_plans as router_module
    from app.clients.kor_travel_map_curation import (
        CurationCollectionFetchResult,
        get_curation_snapshot_service_client,
    )
    from app.main import app
    from app.models.curated_plan import CuratedTripPlan, KtmCurationImportReceipt

    admin_id = await _admin(session_factory)
    fake = _FakeSnapshotClient(
        [
            CurationCollectionFetchResult(
                not_modified=False,
                source_etag=ETAG_1,
                snapshot=_snapshot(revision=1, etag=ETAG_1, item_numbers=(1,)),
            )
        ]
    )

    async def _fail_audit(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("audit unavailable")

    app.dependency_overrides[get_curation_snapshot_service_client] = lambda: fake
    monkeypatch.setattr(router_module, "append_admin_audit", _fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await client.post(
                "/admin/notice-plans/imports/kor-travel-map-curation-collections",
                json={"collection_id": str(COLLECTION_ID), "mode": "create"},
                headers={"Idempotency-Key": str(uuid.uuid4())},
                cookies=auth_cookies(admin_id),
            )
        async with session_factory() as db:
            assert await db.scalar(select(func.count(CuratedTripPlan.curated_plan_id))) == 0
            assert await db.scalar(select(func.count(KtmCurationImportReceipt.receipt_id))) == 0
    finally:
        app.dependency_overrides.pop(get_curation_snapshot_service_client, None)


async def test_concurrent_same_key_import_commits_one_effect_and_replays(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import (
        CurationCollectionFetchResult,
        get_curation_snapshot_service_client,
    )
    from app.main import app
    from app.models.audit import AdminAuditLog
    from app.models.curated_plan import CuratedTripPlan, KtmCurationImportReceipt

    admin_id = await _admin(session_factory)
    fake = _ConcurrentSnapshotClient(
        CurationCollectionFetchResult(
            not_modified=False,
            source_etag=ETAG_1,
            snapshot=_snapshot(revision=1, etag=ETAG_1, item_numbers=(1,)),
        )
    )
    app.dependency_overrides[get_curation_snapshot_service_client] = lambda: fake
    idempotency_key = uuid.uuid4()

    async def _send():  # type: ignore[no-untyped-def]
        return await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curation-collections",
            json={"collection_id": str(COLLECTION_ID), "mode": "create"},
            headers={"Idempotency-Key": str(idempotency_key)},
            cookies=auth_cookies(admin_id),
        )

    try:
        first, second = await asyncio.gather(_send(), _send())
        assert first.status_code == second.status_code == 201, (
            first.text,
            second.text,
        )
        assert first.json() == second.json()
        assert fake.calls == 2
        async with session_factory() as db:
            assert await db.scalar(select(func.count(CuratedTripPlan.curated_plan_id))) == 1
            assert await db.scalar(select(func.count(KtmCurationImportReceipt.receipt_id))) == 1
            assert await db.scalar(select(func.count(AdminAuditLog.log_id))) == 1
    finally:
        app.dependency_overrides.pop(get_curation_snapshot_service_client, None)
