"""Trip API 통합 테스트 — create / get / list / 낙관적 락 (SPRINT-2 DoD)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_create_and_get_trip(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)

    resp = await client.post(
        "/trips",
        json={"title": "부산 2박 3일", "region_hint": "부산", "visibility": "private"},
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    trip = resp.json()["data"]
    assert trip["title"] == "부산 2박 3일"
    assert trip["owner_user_id"] == user_id
    assert trip["version"] == 1

    trip_id = trip["trip_id"]
    got = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert got.status_code == 200
    assert got.json()["data"]["trip_id"] == trip_id


async def test_list_trips_only_owner(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    for i in range(3):
        r = await client.post("/trips", json={"title": f"여행 {i}"}, cookies=cookies)
        assert r.status_code == 201

    resp = await client.get("/trips", cookies=cookies)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 3


async def test_trip_requires_auth(client) -> None:
    resp = await client.post("/trips", json={"title": "익명"})
    assert resp.status_code == 401


async def test_trip_optimistic_lock(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "원본"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    # 올바른 version → 성공
    ok = await client.patch(
        f"/trips/{trip_id}",
        json={"title": "수정본"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["version"] == 2

    # stale version → 409
    conflict = await client.patch(
        f"/trips/{trip_id}",
        json={"title": "다시 수정"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert conflict.status_code == 409


async def test_share_link_uses_web_base_url(
    client,
    verified_user,
    auth_cookies,
    monkeypatch,
) -> None:
    from app.api.v1 import trips as trips_router

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    monkeypatch.setattr(
        trips_router.settings,
        "tripmate_web_base_url",
        "https://tripmate.example",
    )
    created = await client.post("/trips", json={"title": "공유 여행"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    resp = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={"visibility": "view_only"},
        cookies=cookies,
    )

    assert resp.status_code == 201, resp.text
    share = resp.json()["data"]
    assert share["url"].startswith(f"https://tripmate.example/trips/{trip_id}/shared/")
    assert "app.tripmate.local" not in share["url"]


async def test_other_user_cannot_access(
    client, verified_user, auth_cookies, session_factory
) -> None:
    owner_id, _ = verified_user
    created = await client.post("/trips", json={"title": "비공개"}, cookies=auth_cookies(owner_id))
    trip_id = created.json()["data"]["trip_id"]

    # 다른 사용자
    import uuid
    from datetime import UTC, datetime

    from app.models.user import User

    async with session_factory() as db:
        other = User(
            email=f"other_{uuid.uuid4().hex[:8]}@tripmate.test",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_id = str(other.user_id)

    resp = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(other_id))
    assert resp.status_code == 403
