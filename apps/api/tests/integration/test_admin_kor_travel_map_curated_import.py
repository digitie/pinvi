"""kor-travel-map curated feature → Pinvi notice plan import 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class _FakeKorTravelMapClient:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.seen: list[str] = []

    async def get_curated_detail_snapshot(self, curated_feature_id: str) -> dict[str, Any]:
        self.seen.append(curated_feature_id)
        return self.snapshot


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"kor_travel_map_import_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="관리자",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


def _feature_snapshot(*, name: str, lon: float, lat: float) -> dict[str, Any]:
    """Map `CuratedFeatureDetailFeatureSnapshotView`가 실제로 내보내는 key 집합.

    T-VN-H07D 이전 fixture는 `{"display_name": ...}`였는데, Map view가 `extra="forbid"`로
    타입화되면서 그 shape는 **더 이상 나올 수 없다**. 실제 payload와 어긋난 fixture는
    소비자 회귀(예: `extract_feature_label`이 `name`을 읽는다)를 통과시켜 버린다.
    """
    return {
        "feature_id": "feature::festival::busan",
        "name": name,
        "category": "festival",
        "kind": "event",
        "lon": lon,
        "lat": lat,
        "sido_code": "26",
        "sigungu_code": "26350",
        "legal_dong_code": None,
        "address": {"road": "부산광역시 수영구 광안해변로"},
        "detail": {},
    }


def _snapshot() -> dict[str, Any]:
    """Map admin detail-snapshot의 **핀된 계약 shape**를 그대로 따르는 fixture.

    계약은 `apps/api/tests/contract/kor-travel-map-openapi-admin-detail-snapshot.json`가 정본이고
    `tests/unit/test_kor_travel_map_admin_contract.py`가 고정한다.
    """
    return {
        "curated_feature_id": "festival::busan::2026",
        "version": 7,
        "etag": "sha256:abc123",
        "updated_at": "2026-06-12T00:00:00+09:00",
        "theme": {"theme_slug": "festival", "theme_name": "축제"},
        "content": {
            "title": "부산 축제 코스",
            "summary": "광안리와 해운대를 잇는 축제 일정",
            "destination_name": "부산",
            "region_code": "26",
            "category": "festival",
            # T-VN-H07D: typed view에서 required가 된 key(생성부가 항상 내보낸다).
            "curation_status": "curated",
            "reuse_policy": "allowed",
        },
        "source": {
            "provider": "kor-travel-map",
            "source_name": "kor_travel_map curated",
            "dataset_key": "curated_features",
            "source_url": None,
        },
        "items": [
            {
                "curated_feature_item_id": "festival::busan::2026",
                "feature_id": "feature::festival::busan",
                "relation": "primary",
                "sort_order": 1,
                "day_index": 1,
                "memo": "대표 축제",
                "feature_snapshot": _feature_snapshot(
                    name="부산 축제", lon=129.118, lat=35.153
                ),
                "source_record_key": "festival-2026",
            },
            {
                "curated_feature_item_id": "festival::busan::2026::after",
                "feature_id": "feature::gwangalli",
                "relation": "nearby",
                "sort_order": 2,
                "day_index": 1,
                "memo": "근처 산책",
                "feature_snapshot": {
                    **_feature_snapshot(name="광안리", lon=129.128, lat=35.153),
                    "feature_id": "feature::gwangalli",
                },
                "source_record_key": "gwangalli",
            },
        ],
    }


async def test_admin_imports_kor_travel_map_curated_feature_and_upserts(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
    from app.main import app
    from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan

    admin_id = await _admin(session_factory)
    fake = _FakeKorTravelMapClient(_snapshot())
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake
    try:
        created = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curated-features",
            json={
                "curated_feature_id": "festival::busan::2026",
                "mode": "create",
                "is_published": True,
            },
            cookies=auth_cookies(admin_id),
        )
        assert created.status_code == 201, created.text
        data = created.json()["data"]
        assert data["created_plan"] is True
        assert data["source_system"] == "kor-travel-map"
        assert data["source_curated_feature_id"] == "festival::busan::2026"
        assert data["source_version"] == 7
        assert data["source_etag"] == "sha256:abc123"
        assert data["copied_poi_count"] == 2
        assert data["reused_feature_backed_poi_count"] == 0

        plan_id = uuid.UUID(data["notice_plan_id"])
        async with session_factory() as db:
            plan = await db.get(CuratedTripPlan, plan_id)
            assert plan is not None
            assert plan.title == "부산 축제 코스"
            assert plan.category == "festival"
            assert plan.source_system == "kor-travel-map"
            assert plan.source_curated_feature_id == "festival::busan::2026"
            assert plan.source_curated_feature_version == 7
            assert plan.source_etag == "sha256:abc123"
            pois = (
                (
                    await db.execute(
                        select(CuratedPlanPoi)
                        .where(CuratedPlanPoi.curated_plan_id == plan_id)
                        .order_by(CuratedPlanPoi.sort_order)
                    )
                )
                .scalars()
                .all()
            )
            assert len(pois) == 2
            assert {poi.source_curated_feature_item_id for poi in pois} == {
                "festival::busan::2026",
                "festival::busan::2026::after",
            }

        updated = await client.post(
            "/admin/notice-plans/imports/kor-travel-map-curated-features",
            json={"curated_feature_id": "festival::busan::2026", "mode": "upsert"},
            cookies=auth_cookies(admin_id),
        )
        assert updated.status_code == 201, updated.text
        updated_data = updated.json()["data"]
        assert updated_data["created_plan"] is False
        assert updated_data["notice_plan_id"] == str(plan_id)
        assert updated_data["reused_feature_backed_poi_count"] == 2

        async with session_factory() as db:
            poi_count = len(
                (
                    await db.execute(
                        select(CuratedPlanPoi).where(CuratedPlanPoi.curated_plan_id == plan_id)
                    )
                )
                .scalars()
                .all()
            )
            assert poi_count == 2
            plan = await db.get(CuratedTripPlan, plan_id)
            assert plan is not None
            assert plan.is_published is True
    finally:
        app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)
