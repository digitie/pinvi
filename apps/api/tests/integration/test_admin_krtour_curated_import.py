"""krtour-map curated feature → TripMate notice plan import 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class _FakeKrtourClient:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.seen: list[str] = []

    async def get_curated_tripmate_copy(self, curated_feature_id: str) -> dict[str, Any]:
        self.seen.append(curated_feature_id)
        return self.snapshot


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"krtour_import_{uuid.uuid4().hex[:8]}@tripmate.test",
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


def _snapshot() -> dict[str, Any]:
    return {
        "curated_feature_id": "festival::busan::2026",
        "version": 7,
        "etag": "sha256:abc123",
        "updated_at": "2026-06-12T00:00:00+09:00",
        "theme": {"theme_slug": "festival", "theme_name": "축제"},
        "plan": {
            "title": "부산 축제 코스",
            "summary": "광안리와 해운대를 잇는 축제 일정",
            "destination_name": "부산",
            "region_code": "26",
            "category": "festival",
        },
        "source": {
            "provider": "krtour-map",
            "source_name": "krtour curated",
            "dataset_key": "curated_features",
        },
        "items": [
            {
                "curated_feature_item_id": "festival::busan::2026",
                "feature_id": "feature::festival::busan",
                "relation": "primary",
                "sort_order": 1,
                "day_index": 1,
                "memo": "대표 축제",
                "feature_snapshot": {"display_name": "부산 축제"},
                "source_record_key": "festival-2026",
            },
            {
                "curated_feature_item_id": "festival::busan::2026::after",
                "feature_id": "feature::gwangalli",
                "relation": "nearby",
                "sort_order": 2,
                "day_index": 1,
                "memo": "근처 산책",
                "feature_snapshot": {"display_name": "광안리"},
                "source_record_key": "gwangalli",
            },
        ],
    }


async def test_admin_imports_krtour_curated_feature_and_upserts(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.krtour_map import get_krtour_map_client
    from app.main import app
    from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan

    admin_id = await _admin(session_factory)
    fake = _FakeKrtourClient(_snapshot())
    app.dependency_overrides[get_krtour_map_client] = lambda: fake
    try:
        created = await client.post(
            "/admin/notice-plans/imports/krtour-curated-features",
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
        assert data["source_system"] == "krtour-map"
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
            assert plan.source_system == "krtour-map"
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
            "/admin/notice-plans/imports/krtour-curated-features",
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
        app.dependency_overrides.pop(get_krtour_map_client, None)
