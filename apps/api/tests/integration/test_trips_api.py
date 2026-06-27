"""Trip API 통합 테스트 — create / get / list / 낙관적 락 (SPRINT-2 DoD)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

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
        json={
            "title": "부산 2박 3일",
            "region_hint": "부산",
            "primary_region_code": "26110",
            "visibility": "private",
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    trip = resp.json()["data"]
    assert trip["title"] == "부산 2박 3일"
    assert trip["owner_user_id"] == user_id
    assert trip["primary_region_code"] == "26110"
    assert trip["primary_region_source"] == "manual"
    assert trip["version"] == 1

    trip_id = trip["trip_id"]
    got = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert got.status_code == 200
    detail = got.json()["data"]
    assert detail["trip"]["trip_id"] == trip_id
    assert detail["trip"]["primary_region_code"] == "26110"
    assert detail["days"] == []
    assert detail["companions"] == []
    assert detail["share_links"] == []
    assert detail["broken_feature_count"] == 0


async def test_list_trips_only_owner(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    for i in range(3):
        r = await client.post("/trips", json={"title": f"여행 {i}"}, cookies=cookies)
        assert r.status_code == 201

    resp = await client.get("/trips", cookies=cookies)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 3
    assert resp.json()["meta"]["has_more"] is False


async def test_list_trips_bucket_search_and_cursor(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    today = date.today()
    fixtures = [
        {
            "title": "지난 부산 여행",
            "region_hint": "부산",
            "start_date": str(today - timedelta(days=10)),
            "end_date": str(today - timedelta(days=8)),
        },
        {
            "title": "부산 여름 여행",
            "region_hint": "부산",
            "start_date": str(today + timedelta(days=2)),
            "end_date": str(today + timedelta(days=4)),
        },
        {
            "title": "서울 주말 여행",
            "region_hint": "서울",
            "start_date": str(today + timedelta(days=8)),
            "end_date": str(today + timedelta(days=10)),
        },
    ]
    for body in fixtures:
        created = await client.post("/trips", json=body, cookies=cookies)
        assert created.status_code == 201, created.text

    past = await client.get("/trips?bucket=past", cookies=cookies)
    assert past.status_code == 200, past.text
    assert [row["title"] for row in past.json()["data"]] == ["지난 부산 여행"]

    future_busan = await client.get("/trips?bucket=future&q=부산", cookies=cookies)
    assert future_busan.status_code == 200, future_busan.text
    assert [row["title"] for row in future_busan.json()["data"]] == ["부산 여름 여행"]

    first = await client.get("/trips?bucket=all&limit=2", cookies=cookies)
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert len(first_payload["data"]) == 2
    assert first_payload["meta"]["has_more"] is True
    assert first_payload["meta"]["cursor"]

    second = await client.get(
        f"/trips?bucket=all&limit=2&cursor={first_payload['meta']['cursor']}",
        cookies=cookies,
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert len(second_payload["data"]) == 1
    assert second_payload["meta"]["has_more"] is False
    listed_ids = {row["trip_id"] for row in first_payload["data"] + second_payload["data"]}
    assert len(listed_ids) == 3

    invalid_cursor = await client.get("/trips?cursor=not-a-cursor", cookies=cookies)
    assert invalid_cursor.status_code == 422


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


async def test_trip_primary_region_update_and_validation(
    client, verified_user, auth_cookies
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={"title": "지역 여행", "primary_region_code": "11"},
        cookies=cookies,
    )
    assert created.status_code == 201, created.text
    trip = created.json()["data"]
    assert trip["primary_region_code"] == "11"
    assert trip["primary_region_source"] == "manual"

    cleared = await client.patch(
        f"/trips/{trip['trip_id']}",
        json={"primary_region_code": None},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["primary_region_code"] is None
    assert cleared.json()["data"]["primary_region_source"] is None

    invalid = await client.post(
        "/trips",
        json={"title": "잘못된 지역", "primary_region_code": "SEOUL"},
        cookies=cookies,
    )
    assert invalid.status_code == 422


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
        "pinvi_web_base_url",
        "https://pinvi.example",
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
    assert share["url"].startswith(f"https://pinvi.example/trips/{trip_id}/shared/")
    assert "app.pinvi.local" not in share["url"]

    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    share_link = detail.json()["data"]["share_links"][0]
    assert share_link["share_id"] == share["share_id"]
    assert share_link["visibility"] == "view_only"
    assert "token" not in share_link


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

    detail = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner_id))
    assert detail.status_code == 200, detail.text
    companions = detail.json()["data"]["companions"]
    assert [row["companion_id"] for row in companions] == [companion["companion_id"]]

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


async def test_viewer_companion_cannot_write_and_email_masked(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    owner_id, _ = verified_user
    viewer_email = f"viewer_{uuid.uuid4().hex[:8]}@example.com"
    viewer_id = await _create_verified_user(session_factory, viewer_email)
    editor_email = f"editor_{uuid.uuid4().hex[:8]}@example.com"
    editor_id = await _create_verified_user(session_factory, editor_email)
    owner_cookies = auth_cookies(owner_id)

    created = await client.post("/trips", json={"title": "권한 분리"}, cookies=owner_cookies)
    trip_id = created.json()["data"]["trip_id"]
    for email, role in ((viewer_email, "viewer"), (editor_email, "editor")):
        invite = await client.post(
            f"/trips/{trip_id}/members",
            json={"email": email, "role": role},
            cookies=owner_cookies,
        )
        assert invite.status_code == 201, invite.text

    # viewer는 day 생성(쓰기) 불가, editor는 가능.
    day_by_viewer = await client.post(
        f"/trips/{trip_id}/days",
        json={"day_index": 1, "title": "몰래"},
        cookies=auth_cookies(viewer_id),
    )
    assert day_by_viewer.status_code == 403, day_by_viewer.text
    day_by_editor = await client.post(
        f"/trips/{trip_id}/days",
        json={"day_index": 1, "title": "editor day"},
        cookies=auth_cookies(editor_id),
    )
    assert day_by_editor.status_code == 201, day_by_editor.text

    # viewer 상세 — 다른 동반자 invited_email 마스킹 + share_links 비노출.
    viewer_detail = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(viewer_id))
    assert viewer_detail.status_code == 200, viewer_detail.text
    viewer_data = viewer_detail.json()["data"]
    assert all(row["invited_email"] is None for row in viewer_data["companions"])
    assert viewer_data["share_links"] == []

    # owner 상세 — invited_email 노출.
    owner_detail = await client.get(f"/trips/{trip_id}", cookies=owner_cookies)
    owner_emails = {row["invited_email"] for row in owner_detail.json()["data"]["companions"]}
    assert viewer_email in owner_emails


def _attachment_payload(
    user_id: str,
    filename: str = "trip-cover.jpg",
    *,
    purpose: str = "trip_attachment",
    byte_size: int = 1234,
) -> dict[str, object]:
    return {
        "bucket": "pinvi-media",
        "storage_key": f"user-uploads/{purpose}/{user_id}/2026/06/{uuid.uuid4().hex}.jpg",
        "original_filename": filename,
        "content_type": "image/jpeg",
        "byte_size": byte_size,
        "role": "image",
        "description": "테스트 첨부",
        "sort_order": 0,
    }


def _poi_payload(day_index: int, sort_order: str, lon: float, lat: float) -> dict[str, object]:
    return {
        "day_index": day_index,
        "sort_order": sort_order,
        "feature_id": f"feature-{uuid.uuid4().hex}",
        "feature_snapshot": {
            "name": f"POI {sort_order}",
            "coord": {"longitude": lon, "latitude": lat},
        },
    }


async def test_trip_day_crud_and_delete_cascades_pois(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "day CRUD"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    day = await client.post(
        f"/trips/{trip_id}/days",
        json={"day_index": 1, "date": "2026-06-10", "title": "첫날"},
        cookies=cookies,
    )
    assert day.status_code == 201, day.text
    assert day.json()["data"]["title"] == "첫날"

    patched = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"title": "도착일", "note": "비행기"},
        cookies=cookies,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["note"] == "비행기"

    poi = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "a", 126.978, 37.5665),
        cookies=cookies,
    )
    assert poi.status_code == 201, poi.text

    deleted = await client.request("DELETE", f"/trips/{trip_id}/days/1", cookies=cookies)
    assert deleted.status_code == 204
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["days"] == []


async def test_trip_copy_shared_view_and_attachments(
    client,
    verified_user,
    auth_cookies,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={
            "title": "원본 여행",
            "start_date": "2026-06-10",
            "end_date": "2026-06-10",
        },
        cookies=cookies,
    )
    trip_id = created.json()["data"]["trip_id"]
    day = await client.post(
        f"/trips/{trip_id}/days",
        json={"day_index": 1, "date": "2026-06-10", "title": "원본 day"},
        cookies=cookies,
    )
    assert day.status_code == 201, day.text
    poi = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "a", 126.978, 37.5665),
        cookies=cookies,
    )
    poi_id = poi.json()["data"]["attachment_id"]

    trip_attachment = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id),
        cookies=cookies,
    )
    assert trip_attachment.status_code == 201, trip_attachment.text
    poi_attachment = await client.post(
        f"/trips/{trip_id}/pois/{poi_id}/attachments",
        json=_attachment_payload(user_id, "poi.jpg", purpose="poi_attachment"),
        cookies=cookies,
    )
    assert poi_attachment.status_code == 201, poi_attachment.text

    copied = await client.post(
        f"/trips/{trip_id}/copy",
        json={"title": "복사본", "scope": "all", "date_shift_days": 7},
        cookies=cookies,
    )
    assert copied.status_code == 201, copied.text
    copy_data = copied.json()["data"]
    copied_trip_id = copy_data["trip"]["trip_id"]
    assert copy_data["created_trip"] is True
    assert copy_data["copied_day_count"] == 1
    assert copy_data["copied_poi_count"] == 1
    assert copy_data["copied_attachment_count"] == 2
    assert copy_data["trip"]["start_date"] == "2026-06-17"

    copied_detail = await client.get(f"/trips/{copied_trip_id}", cookies=cookies)
    copied_day = copied_detail.json()["data"]["days"][0]
    assert copied_day["date"] == "2026-06-17"
    copied_poi_id = copied_day["pois"][0]["poi_id"]

    copied_trip_attachments = await client.get(
        f"/trips/{copied_trip_id}/attachments",
        cookies=cookies,
    )
    assert copied_trip_attachments.status_code == 200, copied_trip_attachments.text
    assert (
        copied_trip_attachments.json()["data"][0]["source_attachment_id"]
        == (trip_attachment.json()["data"]["attachment_id"])
    )
    copied_poi_attachments = await client.get(
        f"/trips/{copied_trip_id}/pois/{copied_poi_id}/attachments",
        cookies=cookies,
    )
    assert copied_poi_attachments.status_code == 200, copied_poi_attachments.text
    assert (
        copied_poi_attachments.json()["data"][0]["source_attachment_id"]
        == (poi_attachment.json()["data"]["attachment_id"])
    )

    share = await client.post(
        f"/trips/{copied_trip_id}/share-tokens",
        json={"visibility": "view_only"},
        cookies=cookies,
    )
    token = share.json()["data"]["token"]
    shared = await client.get(f"/trips/{copied_trip_id}/shared/{token}")
    assert shared.status_code == 200, shared.text
    shared_data = shared.json()["data"]
    assert shared_data["visibility"] == "view_only"
    assert shared_data["trip"]["trip_id"] == copied_trip_id
    assert "share_links" not in shared_data
    assert "companions" not in shared_data

    removed = await client.delete(
        f"/trips/{copied_trip_id}/attachments/{copied_trip_attachments.json()['data'][0]['attachment_id']}",
        cookies=cookies,
    )
    assert removed.status_code == 204
    after_delete = await client.get(f"/trips/{copied_trip_id}/attachments", cookies=cookies)
    assert after_delete.json()["data"] == []


async def test_trip_copy_all_includes_auto_created_day_rows(
    client,
    verified_user,
    auth_cookies,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "day row 없는 여행"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]
    poi = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(2, "a", 126.978, 37.5665),
        cookies=cookies,
    )
    assert poi.status_code == 201, poi.text

    copied = await client.post(
        f"/trips/{trip_id}/copy",
        json={"title": "복사본", "scope": "all"},
        cookies=cookies,
    )
    assert copied.status_code == 201, copied.text
    copy_data = copied.json()["data"]
    assert copy_data["copied_day_count"] == 1
    assert copy_data["copied_poi_count"] == 1

    copied_detail = await client.get(
        f"/trips/{copy_data['trip']['trip_id']}",
        cookies=cookies,
    )
    assert copied_detail.status_code == 200, copied_detail.text
    assert copied_detail.json()["data"]["days"][0]["day_index"] == 2


async def test_trip_day_distance_matrix_and_optimize(
    client,
    verified_user,
    auth_cookies,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "최적화 여행"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]
    first = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "a", 126.0, 37.0),
        cookies=cookies,
    )
    second = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "b", 128.0, 37.0),
        cookies=cookies,
    )
    third = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "c", 126.1, 37.0),
        cookies=cookies,
    )
    first_id = first.json()["data"]["attachment_id"]
    second_id = second.json()["data"]["attachment_id"]
    third_id = third.json()["data"]["attachment_id"]

    matrix = await client.get(f"/trips/{trip_id}/days/1/distance-matrix", cookies=cookies)
    assert matrix.status_code == 200, matrix.text
    distances = matrix.json()["data"]["distances_meters"]
    assert len(distances) == 3
    assert distances[0][0] == 0
    assert distances[0][2] < distances[0][1]

    optimized = await client.post(
        f"/trips/{trip_id}/days/1/optimize",
        json={"start_poi_id": first_id, "persist": True},
        cookies=cookies,
    )
    assert optimized.status_code == 200, optimized.text
    assert optimized.json()["data"]["ordered_poi_ids"] == [first_id, third_id, second_id]
    assert optimized.json()["data"]["moves"]

    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    pois = detail.json()["data"]["days"][0]["pois"]
    assert [poi["poi_id"] for poi in pois] == [first_id, third_id, second_id]


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


async def test_trip_attachment_limit_and_reorder(
    client,
    verified_user,
    auth_cookies,
    monkeypatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "pinvi_max_attachments_per_target", 2)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "첨부 한도"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    a1 = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "a1.jpg"),
        cookies=cookies,
    )
    assert a1.status_code == 201, a1.text
    a2 = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "a2.jpg"),
        cookies=cookies,
    )
    assert a2.status_code == 201

    # 한도(2) 초과 → 409.
    a3 = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "a3.jpg"),
        cookies=cookies,
    )
    assert a3.status_code == 409, a3.text
    assert a3.json()["error"]["code"] == "ATTACHMENT_LIMIT_EXCEEDED"

    # 재정렬: a1을 sort_order=10으로 → 목록에서 a2(0)가 먼저.
    a1_id = a1.json()["data"]["attachment_id"]
    a2_id = a2.json()["data"]["attachment_id"]
    patched = await client.patch(
        f"/trips/{trip_id}/attachments/{a1_id}",
        json={"sort_order": 10},
        cookies=cookies,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["sort_order"] == 10

    listed = await client.get(f"/trips/{trip_id}/attachments", cookies=cookies)
    ids = [row["attachment_id"] for row in listed.json()["data"]]
    assert ids == [a2_id, a1_id]


async def test_trip_attachment_rejects_unowned_storage_ref(
    client,
    verified_user,
    auth_cookies,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "첨부 검증"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    wrong_user_payload = _attachment_payload(str(uuid.uuid4()), "other.jpg")
    wrong_user = await client.post(
        f"/trips/{trip_id}/attachments",
        json=wrong_user_payload,
        cookies=cookies,
    )
    assert wrong_user.status_code == 422, wrong_user.text
    assert wrong_user.json()["error"]["code"] == "INVALID_ATTACHMENT_STORAGE_REF"

    wrong_bucket_payload = {
        **_attachment_payload(user_id, "bucket.jpg"),
        "bucket": "other-bucket",
    }
    wrong_bucket = await client.post(
        f"/trips/{trip_id}/attachments",
        json=wrong_bucket_payload,
        cookies=cookies,
    )
    assert wrong_bucket.status_code == 422, wrong_bucket.text
    assert wrong_bucket.json()["error"]["code"] == "INVALID_ATTACHMENT_STORAGE_REF"


async def test_trip_attachment_download_url(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "다운로드"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]
    payload = _attachment_payload(user_id, "dl.jpg")
    att = await client.post(f"/trips/{trip_id}/attachments", json=payload, cookies=cookies)
    assert att.status_code == 201, att.text
    att_id = att.json()["data"]["attachment_id"]

    resp = await client.get(f"/trips/{trip_id}/attachments/{att_id}/download-url", cookies=cookies)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["method"] == "GET"
    assert data["bucket"] == payload["bucket"]
    assert data["storage_key"] == payload["storage_key"]
    assert payload["storage_key"] in data["download_url"]

    # 없는 첨부 → 404
    missing = await client.get(
        f"/trips/{trip_id}/attachments/{uuid.uuid4()}/download-url", cookies=cookies
    )
    assert missing.status_code == 404


async def test_trip_day_poi_and_user_file_libraries(
    client,
    verified_user,
    auth_cookies,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "파일 모음"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]
    day = await client.post(
        f"/trips/{trip_id}/days",
        json={"day_index": 1, "date": "2026-06-10", "title": "파일 day"},
        cookies=cookies,
    )
    assert day.status_code == 201, day.text
    poi = await client.post(
        f"/trips/{trip_id}/pois",
        json=_poi_payload(1, "a", 126.978, 37.5665),
        cookies=cookies,
    )
    assert poi.status_code == 201, poi.text
    poi_id = poi.json()["data"]["attachment_id"]

    trip_attachment = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "trip.jpg"),
        cookies=cookies,
    )
    assert trip_attachment.status_code == 201, trip_attachment.text
    day_attachment = await client.post(
        f"/trips/{trip_id}/days/1/attachments",
        json=_attachment_payload(
            user_id,
            "day.jpg",
            purpose="trip_day_attachment",
        ),
        cookies=cookies,
    )
    assert day_attachment.status_code == 201, day_attachment.text
    poi_attachment = await client.post(
        f"/trips/{trip_id}/pois/{poi_id}/attachments",
        json=_attachment_payload(user_id, "poi.jpg", purpose="poi_attachment"),
        cookies=cookies,
    )
    assert poi_attachment.status_code == 201, poi_attachment.text

    day_list = await client.get(f"/trips/{trip_id}/days/1/attachments", cookies=cookies)
    assert day_list.status_code == 200, day_list.text
    assert day_list.json()["data"][0]["trip_day_index"] == 1

    trip_files = await client.get(f"/trips/{trip_id}/files", cookies=cookies)
    assert trip_files.status_code == 200, trip_files.text
    trip_file_data = trip_files.json()["data"]
    assert trip_file_data["total"] == 3
    assert {row["target_scope"] for row in trip_file_data["items"]} == {"trip", "day", "poi"}

    user_files = await client.get("/users/me/files", cookies=cookies)
    assert user_files.status_code == 200, user_files.text
    user_file_data = user_files.json()["data"]
    assert user_file_data["total"] == 3
    assert {row["original_filename"] for row in user_file_data["items"]} == {
        "trip.jpg",
        "day.jpg",
        "poi.jpg",
    }

    day_attachment_id = day_attachment.json()["data"]["attachment_id"]
    day_download = await client.get(
        f"/trips/{trip_id}/days/1/attachments/{day_attachment_id}/download-url",
        cookies=cookies,
    )
    assert day_download.status_code == 200, day_download.text
    assert day_download.json()["data"]["method"] == "GET"

    poi_attachment_id = poi_attachment.json()["data"]["attachment_id"]
    user_download = await client.get(
        f"/users/me/files/{poi_attachment_id}/download-url",
        cookies=cookies,
    )
    assert user_download.status_code == 200, user_download.text
    assert user_download.json()["data"]["storage_key"].endswith(".jpg")

    deleted = await client.delete(f"/users/me/files/{poi_attachment_id}", cookies=cookies)
    assert deleted.status_code == 204
    after_delete = await client.get("/users/me/files", cookies=cookies)
    assert after_delete.status_code == 200
    assert after_delete.json()["data"]["total"] == 2

    trip_level_attachment_id = trip_attachment.json()["data"]["attachment_id"]
    trip_level_delete = await client.delete(
        f"/trips/{trip_id}/attachments/{trip_level_attachment_id}",
        cookies=cookies,
    )
    assert trip_level_delete.status_code == 204


async def test_attachment_upload_url_and_trip_quota_overrides(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    from sqlalchemy import select

    from app.models.user import User
    from app.services.storage_policy import get_storage_settings

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "quota"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    async with session_factory() as db:
        settings_row = await get_storage_settings(db)
        settings_row.attachment_max_upload_bytes = 1000
        settings_row.trip_attachment_quota_bytes = 5000
        settings_row.user_attachment_quota_bytes = 5000
        await db.commit()

    too_large_url = await client.post(
        "/storage/upload-urls",
        json={
            "purpose": "trip_attachment",
            "filename": "too-large.jpg",
            "content_type": "image/jpeg",
            "content_length": 1001,
        },
        cookies=cookies,
    )
    assert too_large_url.status_code == 422, too_large_url.text
    assert too_large_url.json()["error"]["code"] == "FILE_TOO_LARGE"

    async with session_factory() as db:
        settings_row = await get_storage_settings(db)
        settings_row.attachment_max_upload_bytes = 2000
        settings_row.trip_attachment_quota_bytes = 1500
        settings_row.user_attachment_quota_bytes = 5000
        await db.commit()

    first = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "first.jpg", byte_size=900),
        cookies=cookies,
    )
    assert first.status_code == 201, first.text

    quota_blocked = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "second.jpg", byte_size=700),
        cookies=cookies,
    )
    assert quota_blocked.status_code == 409, quota_blocked.text
    assert quota_blocked.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        assert user is not None
        user.attachment_max_upload_bytes_override = 3000
        user.trip_attachment_quota_bytes_override = 3000
        user.user_attachment_quota_bytes_override = 5000
        await db.commit()

    override_url = await client.post(
        "/storage/upload-urls",
        json={
            "purpose": "trip_attachment",
            "filename": "allowed-by-user-override.jpg",
            "content_type": "image/jpeg",
            "content_length": 2500,
        },
        cookies=cookies,
    )
    assert override_url.status_code == 200, override_url.text
    assert override_url.json()["data"]["max_upload_bytes"] == 3000

    second = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(user_id, "second.jpg", byte_size=700),
        cookies=cookies,
    )
    assert second.status_code == 201, second.text
