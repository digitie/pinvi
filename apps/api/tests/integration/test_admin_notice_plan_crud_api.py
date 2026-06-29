"""`/admin/notice-plans` 추천 여행 작성기 CRUD 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.asyncio


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"notice_plan_admin_{uuid.uuid4().hex[:8]}@pinvi.test",
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


async def test_admin_notice_plan_crud_and_poi_editor(client, session_factory, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    cookies = auth_cookies(admin_id)
    slug = f"seoul-cafe-{uuid.uuid4().hex[:8]}"

    created = await client.post(
        "/admin/notice-plans",
        json={
            "slug": slug,
            "title": "서울 카페 산책",
            "category": "cafe",
            "summary": "성수와 한남을 잇는 반나절 코스",
            "destination": "서울",
            "starts_on": "2026-07-01",
            "ends_on": "2026-07-02",
            "is_published": False,
        },
        cookies=cookies,
    )
    assert created.status_code == 201, created.text
    plan = created.json()["data"]
    plan_id = plan["notice_plan_id"]
    assert plan["version"] == 1
    assert plan["pois"] == []

    listed = await client.get(f"/admin/notice-plans?q={slug}", cookies=cookies)
    assert listed.status_code == 200, listed.text
    assert [item["notice_plan_id"] for item in listed.json()["data"]] == [plan_id]

    patched = await client.patch(
        f"/admin/notice-plans/{plan_id}",
        json={"title": "서울 카페 큐레이션", "is_published": True},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["version"] == 2
    assert patched.json()["data"]["is_published"] is True

    stale = await client.patch(
        f"/admin/notice-plans/{plan_id}",
        json={"title": "stale"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    poi_created = await client.post(
        f"/admin/notice-plans/{plan_id}/pois",
        json={
            "day_index": 1,
            "sort_order": "001000",
            "feature_id": None,
            "feature_snapshot": {"display_name": "성수 카페"},
            "memo": "오전 방문",
            "budget_amount": "12000",
            "currency": "KRW",
            "user_url": "https://example.com/cafe",
            "custom_marker_color": "P-07",
            "custom_marker_icon": "cafe",
        },
        cookies=cookies,
    )
    assert poi_created.status_code == 201, poi_created.text
    poi = poi_created.json()["data"]
    poi_id = poi["notice_poi_id"]
    assert poi["memo"] == "오전 방문"

    poi_updated = await client.patch(
        f"/admin/notice-plans/{plan_id}/pois/{poi_id}",
        json={"memo": "오후 방문", "sort_order": "002000"},
        headers={"If-Match": str(poi["version"])},
        cookies=cookies,
    )
    assert poi_updated.status_code == 200, poi_updated.text
    assert poi_updated.json()["data"]["version"] == poi["version"] + 1
    assert poi_updated.json()["data"]["memo"] == "오후 방문"

    reordered = await client.post(
        f"/admin/notice-plans/{plan_id}/pois/reorder",
        json={"items": [{"notice_poi_id": poi_id, "day_index": 2, "sort_order": "000500"}]},
        cookies=cookies,
    )
    assert reordered.status_code == 200, reordered.text
    assert reordered.json()["data"][0]["day_index"] == 2
    assert reordered.json()["data"][0]["sort_order"] == "000500"

    detail = await client.get(f"/admin/notice-plans/{plan_id}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["pois"][0]["notice_poi_id"] == poi_id
    poi_version = detail.json()["data"]["pois"][0]["version"]

    deleted_poi = await client.request(
        "DELETE",
        f"/admin/notice-plans/{plan_id}/pois/{poi_id}",
        headers={"If-Match": str(poi_version)},
        cookies=cookies,
    )
    assert deleted_poi.status_code == 204, deleted_poi.text

    detail_after_poi_delete = await client.get(f"/admin/notice-plans/{plan_id}", cookies=cookies)
    assert detail_after_poi_delete.status_code == 200, detail_after_poi_delete.text
    assert detail_after_poi_delete.json()["data"]["pois"] == []
    plan_version = detail_after_poi_delete.json()["data"]["version"]

    deleted_plan = await client.request(
        "DELETE",
        f"/admin/notice-plans/{plan_id}",
        headers={"If-Match": str(plan_version)},
        cookies=cookies,
    )
    assert deleted_plan.status_code == 204, deleted_plan.text

    listed_after_delete = await client.get(f"/admin/notice-plans?q={slug}", cookies=cookies)
    assert listed_after_delete.status_code == 200, listed_after_delete.text
    assert listed_after_delete.json()["data"] == []
