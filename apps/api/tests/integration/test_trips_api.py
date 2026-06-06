"""Trip API 통합 테스트 — create / get / list / 낙관적 락 (SPRINT-2 DoD)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.asyncio


async def _create_verified_user(session_factory, email: str) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=email,
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


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


async def test_owner_can_invite_existing_user_and_queue_trip_invite(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    from sqlalchemy import select

    from app.models.email_queue import EmailQueue

    owner_id, _ = verified_user
    companion_email = f"friend_{uuid.uuid4().hex[:8]}@example.com"
    companion_id = await _create_verified_user(session_factory, companion_email)

    created = await client.post(
        "/trips",
        json={"title": "동반자 여행"},
        cookies=auth_cookies(owner_id),
    )
    trip_id = created.json()["data"]["trip_id"]

    resp = await client.post(
        f"/trips/{trip_id}/members",
        json={"email": companion_email, "display_name": "친구", "role": "viewer"},
        cookies=auth_cookies(owner_id),
    )

    assert resp.status_code == 201, resp.text
    companion = resp.json()["data"]
    assert companion["user_id"] == companion_id
    assert companion["invited_email"] == companion_email
    assert companion["joined_at"] is not None

    async with session_factory() as db:
        queued = await db.scalar(
            select(EmailQueue).where(
                EmailQueue.to_email == companion_email,
                EmailQueue.template == "trip_invite",
            )
        )
        assert queued is not None
        assert queued.payload["trip_id"] == trip_id
        assert queued.payload["companion_id"] == companion["companion_id"]


async def test_companion_cannot_invite_or_issue_share_link(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    owner_id, _ = verified_user
    companion_email = f"viewer_{uuid.uuid4().hex[:8]}@example.com"
    companion_id = await _create_verified_user(session_factory, companion_email)
    owner_cookies = auth_cookies(owner_id)

    created = await client.post("/trips", json={"title": "권한 여행"}, cookies=owner_cookies)
    trip_id = created.json()["data"]["trip_id"]
    invite = await client.post(
        f"/trips/{trip_id}/members",
        json={"email": companion_email, "role": "viewer"},
        cookies=owner_cookies,
    )
    assert invite.status_code == 201

    companion_cookies = auth_cookies(companion_id)
    invite_by_companion = await client.post(
        f"/trips/{trip_id}/members",
        json={"email": f"other_{uuid.uuid4().hex[:8]}@example.com", "role": "viewer"},
        cookies=companion_cookies,
    )
    assert invite_by_companion.status_code == 403

    share_by_companion = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={"visibility": "comment"},
        cookies=companion_cookies,
    )
    assert share_by_companion.status_code == 403


async def test_companion_can_comment_and_owner_can_delete(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    owner_id, _ = verified_user
    companion_email = f"commenter_{uuid.uuid4().hex[:8]}@example.com"
    companion_id = await _create_verified_user(session_factory, companion_email)
    owner_cookies = auth_cookies(owner_id)

    created = await client.post("/trips", json={"title": "댓글 여행"}, cookies=owner_cookies)
    trip_id = created.json()["data"]["trip_id"]
    invite = await client.post(
        f"/trips/{trip_id}/members",
        json={"email": companion_email, "role": "viewer"},
        cookies=owner_cookies,
    )
    assert invite.status_code == 201

    comment = await client.post(
        f"/trips/{trip_id}/comments",
        json={"body": "  일정 확인했습니다.  ", "target_type": "trip"},
        cookies=auth_cookies(companion_id),
    )
    assert comment.status_code == 201, comment.text
    comment_data = comment.json()["data"]
    assert comment_data["body"] == "일정 확인했습니다."
    assert comment_data["author_user_id"] == companion_id

    comments = await client.get(f"/trips/{trip_id}/comments", cookies=owner_cookies)
    assert comments.status_code == 200
    assert [row["comment_id"] for row in comments.json()["data"]] == [comment_data["comment_id"]]

    deleted = await client.delete(
        f"/trips/{trip_id}/comments/{comment_data['comment_id']}",
        cookies=owner_cookies,
    )
    assert deleted.status_code == 204
    after_delete = await client.get(f"/trips/{trip_id}/comments", cookies=owner_cookies)
    assert after_delete.json()["data"] == []


async def test_other_user_cannot_access(
    client, verified_user, auth_cookies, session_factory
) -> None:
    owner_id, _ = verified_user
    created = await client.post("/trips", json={"title": "비공개"}, cookies=auth_cookies(owner_id))
    trip_id = created.json()["data"]["trip_id"]

    # 다른 사용자
    from app.models.user import User

    async with session_factory() as db:
        other = User(
            email=f"other_{uuid.uuid4().hex[:8]}@example.com",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_id = str(other.user_id)

    resp = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(other_id))
    assert resp.status_code == 403
