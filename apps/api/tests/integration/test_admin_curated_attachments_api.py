"""`/admin/notice-plans/*` 큐레이션 첨부 통합 테스트 — T-105 #1·#2 (§5.3/5.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"curated_{uuid.uuid4().hex[:8]}@pinvi.test",
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


async def _seed_plan_poi(session_factory, *, admin_id: str) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan

    async with session_factory() as db:
        plan = CuratedTripPlan(
            slug=f"plan-{uuid.uuid4().hex[:8]}",
            title="추천 코스",
            created_by_admin_id=uuid.UUID(admin_id),
            updated_by_admin_id=uuid.UUID(admin_id),
        )
        db.add(plan)
        await db.flush()
        poi = CuratedPlanPoi(
            curated_plan_id=plan.curated_plan_id,
            day_index=1,
            sort_order="n",
            feature_snapshot={"name": "해운대"},
        )
        db.add(poi)
        await db.commit()
        return str(plan.curated_plan_id), str(poi.curated_poi_id)


def _body(user_id: str, purpose: str = "curated_plan_attachment", **over: Any) -> dict[str, Any]:
    base = {
        "bucket": "pinvi-media",
        "storage_key": f"user-uploads/{purpose}/{user_id}/2026/06/{uuid.uuid4().hex}.jpg",
        "original_filename": "cover.jpg",
        "content_type": "image/jpeg",
        "byte_size": 1024,
        "role": "image",
        "sort_order": 0,
    }
    base.update(over)
    return base


async def test_plan_attachment_crud(client, session_factory, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    plan_id, _ = await _seed_plan_poi(session_factory, admin_id=admin_id)
    cookies = auth_cookies(admin_id)

    # 빈 목록
    r0 = await client.get(f"/admin/notice-plans/{plan_id}/attachments", cookies=cookies)
    assert r0.status_code == 200, r0.text
    assert r0.json()["data"] == []

    # 생성 201 — curated/notice alias 동기
    r1 = await client.post(
        f"/admin/notice-plans/{plan_id}/attachments", json=_body(admin_id), cookies=cookies
    )
    assert r1.status_code == 201, r1.text
    created = r1.json()["data"]
    assert created["curated_plan_id"] == plan_id
    assert created["notice_plan_id"] == plan_id
    assert created["curated_poi_id"] is None
    attachment_id = created["attachment_id"]

    # 목록 1건
    r2 = await client.get(f"/admin/notice-plans/{plan_id}/attachments", cookies=cookies)
    assert len(r2.json()["data"]) == 1

    # 삭제 204 → 목록 다시 비어야 함(soft delete)
    r3 = await client.request(
        "DELETE",
        f"/admin/notice-plans/{plan_id}/attachments/{attachment_id}",
        cookies=cookies,
    )
    assert r3.status_code == 204, r3.text
    r4 = await client.get(f"/admin/notice-plans/{plan_id}/attachments", cookies=cookies)
    assert r4.json()["data"] == []


async def test_poi_attachment_crud(client, session_factory, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    plan_id, poi_id = await _seed_plan_poi(session_factory, admin_id=admin_id)
    cookies = auth_cookies(admin_id)

    r1 = await client.post(
        f"/admin/notice-plans/{plan_id}/pois/{poi_id}/attachments",
        json=_body(admin_id, "curated_poi_attachment"),
        cookies=cookies,
    )
    assert r1.status_code == 201, r1.text
    created = r1.json()["data"]
    assert created["curated_poi_id"] == poi_id
    assert created["notice_poi_id"] == poi_id
    assert created["curated_plan_id"] is None

    r2 = await client.get(
        f"/admin/notice-plans/{plan_id}/pois/{poi_id}/attachments", cookies=cookies
    )
    assert len(r2.json()["data"]) == 1


async def test_unknown_plan_404(client, session_factory, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    cookies = auth_cookies(admin_id)
    missing = uuid.uuid4()
    r = await client.post(
        f"/admin/notice-plans/{missing}/attachments", json=_body(admin_id), cookies=cookies
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"


async def test_curated_attachment_rejects_unowned_storage_ref(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    plan_id, poi_id = await _seed_plan_poi(session_factory, admin_id=admin_id)
    cookies = auth_cookies(admin_id)

    wrong_user = await _admin(session_factory)
    plan_resp = await client.post(
        f"/admin/notice-plans/{plan_id}/attachments",
        json=_body(wrong_user),
        cookies=cookies,
    )
    assert plan_resp.status_code == 422, plan_resp.text
    assert plan_resp.json()["error"]["code"] == "INVALID_ATTACHMENT_STORAGE_REF"

    poi_resp = await client.post(
        f"/admin/notice-plans/{plan_id}/pois/{poi_id}/attachments",
        json=_body(admin_id, "curated_plan_attachment"),
        cookies=cookies,
    )
    assert poi_resp.status_code == 422, poi_resp.text
    assert poi_resp.json()["error"]["code"] == "INVALID_ATTACHMENT_STORAGE_REF"


async def test_curated_upload_url_requires_admin(
    client, verified_user, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    body = {
        "filename": "cover.jpg",
        "content_type": "image/jpeg",
        "content_length": 1024,
        "purpose": "curated_plan_attachment",
    }

    hidden = await client.post("/storage/upload-urls", json=body, cookies=auth_cookies(user_id))
    assert hidden.status_code == 404

    admin_id = await _admin(session_factory)
    allowed = await client.post("/storage/upload-urls", json=body, cookies=auth_cookies(admin_id))
    assert allowed.status_code == 200, allowed.text
    data = allowed.json()["data"]
    assert data["bucket"] == "pinvi-media"
    assert data["storage_key"].startswith(f"user-uploads/curated_plan_attachment/{admin_id}/")
    assert "/storage/uploads/" in data["upload_url"]
    assert "127.0.0.1" not in data["upload_url"]


async def test_non_admin_hidden(client, verified_user, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    r = await client.get(
        f"/admin/notice-plans/{uuid.uuid4()}/attachments", cookies=auth_cookies(user_id)
    )
    assert r.status_code == 404
