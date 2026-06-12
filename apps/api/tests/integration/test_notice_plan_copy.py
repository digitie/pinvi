"""Curated trip plan → trip copy 통합 (ADR-013, ADR-029).

curated_plan_pois → trip_day_pois 복사 + 새 trip 생성 / 기존 trip 추가 + 부분 선택.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.curated_plan import CuratedPlanPoi
from app.models.poi import TripDayPoi
from app.models.user import User
from app.services.notice_plan import create_plan_with_pois, ensure_plan_poi_for_feature

pytestmark = pytest.mark.asyncio


async def _admin_id(session_factory) -> uuid.UUID:
    async with session_factory() as db:
        admin = User(
            email=f"admin_{uuid.uuid4().hex[:8]}@tripmate.test",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin.user_id


async def _seed_plan(session_factory) -> uuid.UUID:
    admin_id = await _admin_id(session_factory)
    async with session_factory() as db:
        plan = await create_plan_with_pois(
            db,
            admin_id=admin_id,
            slug=f"busan-{uuid.uuid4().hex[:6]}",
            title="부산 추천 코스",
            destination="부산",
            pois=[
                {
                    "day_index": 1,
                    "sort_order": "a0",
                    "feature_id": "f_haeundae",
                    "budget_amount": Decimal("55000.00"),
                    "currency": "KRW",
                },
                {"day_index": 1, "sort_order": "a1", "feature_id": "f_gwangalli"},
                {"day_index": 2, "sort_order": "a0", "feature_id": "f_taejongdae"},
            ],
        )
        return plan.curated_plan_id


async def test_copy_creates_new_trip(client, verified_user, auth_cookies, session_factory) -> None:
    user_id, _ = verified_user
    plan_id = await _seed_plan(session_factory)

    resp = await client.post(
        f"/notice-plans/{plan_id}/copy",
        json={"trip_title": "내 부산 여행"},
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["created_trip"] is True
    assert len(data["copied_poi_ids"]) == 3

    async with session_factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(TripDayPoi)
            .where(TripDayPoi.trip_id == uuid.UUID(data["trip_id"]))
        )
        assert count == 3
        copied_budget = await db.scalar(
            select(TripDayPoi.budget_amount).where(
                TripDayPoi.trip_id == uuid.UUID(data["trip_id"]),
                TripDayPoi.feature_id == "f_haeundae",
            )
        )
        copied_currency = await db.scalar(
            select(TripDayPoi.currency).where(
                TripDayPoi.trip_id == uuid.UUID(data["trip_id"]),
                TripDayPoi.feature_id == "f_haeundae",
            )
        )
        assert copied_budget == Decimal("55000.00")
        assert copied_currency == "KRW"


async def test_copy_allows_curated_poi_without_feature_id(
    client, verified_user, auth_cookies, session_factory
) -> None:
    user_id, _ = verified_user
    admin_id = await _admin_id(session_factory)
    async with session_factory() as db:
        plan = await create_plan_with_pois(
            db,
            admin_id=admin_id,
            slug=f"free-poi-{uuid.uuid4().hex[:6]}",
            title="자유 장소 코스",
            pois=[
                {
                    "day_index": 1,
                    "sort_order": "a0",
                    "feature_snapshot": {"name": "메모 장소"},
                    "memo": "feature 연결 없이도 curated POI 가능",
                }
            ],
        )
        plan_id = plan.curated_plan_id

    resp = await client.post(
        f"/notice-plans/{plan_id}/copy",
        json={"trip_title": "자유 장소 포함 여행"},
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 201, resp.text
    trip_id = uuid.UUID(resp.json()["data"]["trip_id"])

    async with session_factory() as db:
        copied_feature_id = await db.scalar(
            select(TripDayPoi.feature_id).where(TripDayPoi.trip_id == trip_id)
        )
        assert copied_feature_id is None


async def test_feature_backed_curated_poi_is_created_once_for_external_link(
    session_factory,
) -> None:
    admin_id = await _admin_id(session_factory)
    async with session_factory() as db:
        plan = await create_plan_with_pois(
            db,
            admin_id=admin_id,
            slug=f"agent-link-{uuid.uuid4().hex[:6]}",
            title="외부 연계 코스",
            pois=[],
        )
        first = await ensure_plan_poi_for_feature(
            db,
            curated_plan_id=plan.curated_plan_id,
            feature_id="f_agent_linked",
            day_index=1,
            sort_order="a0",
            feature_snapshot={"name": "연계 장소"},
        )
        second = await ensure_plan_poi_for_feature(
            db,
            curated_plan_id=plan.curated_plan_id,
            feature_id="f_agent_linked",
            day_index=1,
            sort_order="a1",
            feature_snapshot={"name": "중복 요청"},
        )
        assert second.curated_poi_id == first.curated_poi_id

        count = await db.scalar(
            select(func.count())
            .select_from(CuratedPlanPoi)
            .where(
                CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                CuratedPlanPoi.feature_id == "f_agent_linked",
                CuratedPlanPoi.deleted_at.is_(None),
            )
        )
        assert count == 1


async def test_copy_partial_pois(client, verified_user, auth_cookies, session_factory) -> None:
    user_id, _ = verified_user
    plan_id = await _seed_plan(session_factory)

    # plan 상세에서 POI id 확보
    detail = await client.get(f"/notice-plans/{plan_id}", cookies=auth_cookies(user_id))
    assert detail.status_code == 200
    pois = detail.json()["data"]["pois"]
    chosen = [pois[0]["notice_poi_id"]]

    resp = await client.post(
        f"/notice-plans/{plan_id}/copy",
        json={"poi_ids": chosen},
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["data"]["copied_poi_ids"]) == 1


async def test_copy_into_existing_trip(
    client, verified_user, auth_cookies, session_factory
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    plan_id = await _seed_plan(session_factory)

    created = await client.post("/trips", json={"title": "기존 여행"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    resp = await client.post(
        f"/notice-plans/{plan_id}/copy",
        json={"target_trip_id": trip_id},
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["created_trip"] is False
    assert resp.json()["data"]["trip_id"] == trip_id


async def test_unpublished_plan_not_found(
    client, verified_user, auth_cookies, session_factory
) -> None:
    user_id, _ = verified_user
    admin_id = await _admin_id(session_factory)
    async with session_factory() as db:
        plan = await create_plan_with_pois(
            db,
            admin_id=admin_id,
            slug=f"draft-{uuid.uuid4().hex[:6]}",
            title="비공개 코스",
            is_published=False,
            pois=[{"day_index": 1, "sort_order": "a0", "feature_id": "f_x"}],
        )
        plan_id = plan.curated_plan_id

    resp = await client.post(
        f"/notice-plans/{plan_id}/copy",
        json={"trip_title": "시도"},
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 404
