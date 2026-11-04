"""#643 수정 PR(#654~#662) 리뷰 회귀 — 날짜 불변식·휴지통 목록·삭제 경쟁·메모 길이."""

from __future__ import annotations

import uuid

import pytest

from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.services.poi import PoiNotFoundError, create_poi, reorder_pois, update_poi
from app.services.trip import TripNotFoundError, update_trip
from tests.integration.test_pois_reorder import _add_poi

pytestmark = pytest.mark.asyncio


async def _trip(client, cookies, start="2026-11-03", end="2026-11-05") -> str:
    created = await client.post(
        "/trips",
        json={"title": "리뷰 회귀", "start_date": start, "end_date": end},
        cookies=cookies,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["trip_id"]


async def _trip_version(client, cookies, trip_id) -> int:
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    return detail.json()["data"]["trip"]["version"]


async def _soft_delete(client, cookies, trip_id) -> None:
    removed = await client.request(
        "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
    )
    assert removed.status_code == 204, removed.text


async def test_trip_patch_date_messages_are_korean_for_the_dialog(
    client, verified_user, auth_cookies
) -> None:
    """#624: 422 안내는 다이얼로그에 그대로 보이므로 필드 이름이 아니라 한국어 문구여야 한다."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    reversed_range = await client.patch(
        f"/trips/{trip_id}",
        json={"start_date": "2026-11-10", "end_date": "2026-11-04"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert reversed_range.status_code == 422, reversed_range.text
    assert reversed_range.json()["error"]["message"] == "종료일은 시작일 이후여야 합니다."


async def test_shifting_trip_dates_cannot_duplicate_a_day_override(
    client, verified_user, auth_cookies
) -> None:
    """#649 불변식은 여행 기간 수정에도 적용된다 — 파생 날짜가 다른 일자의 지정 날짜와 겹치면 422."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    deleted = await client.delete(
        f"/trips/{trip_id}/days/3", headers={"If-Match": "1"}, cookies=cookies
    )
    assert deleted.status_code == 204, deleted.text
    override = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"date": "2026-11-05"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert override.status_code == 200, override.text
    version = await _trip_version(client, cookies, trip_id)
    shifted = await client.patch(
        f"/trips/{trip_id}",
        json={"start_date": "2026-11-04", "end_date": "2026-11-06"},
        headers={"If-Match": str(version)},
        cookies=cookies,
    )
    # 2일차의 파생 날짜(11-05)가 1일차 지정 날짜(11-05)와 같아진다.
    assert shifted.status_code == 422, shifted.text
    assert shifted.json()["error"]["message"].startswith("1일차와 2일차의 날짜가 겹칩니다.")
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert detail.json()["data"]["trip"]["start_date"] == "2026-11-03"
    # 겹치지 않는 이동은 그대로 허용한다.
    moved = await client.patch(
        f"/trips/{trip_id}",
        json={"start_date": "2026-11-01", "end_date": "2026-11-05"},
        headers={"If-Match": str(version)},
        cookies=cookies,
    )
    assert moved.status_code == 200, moved.text


async def test_trash_list_includes_past_trips_without_bucket(
    client, verified_user, auth_cookies
) -> None:
    """휴지통은 일정 버킷과 무관하다 — `bucket` 기본값(future)이 지난 여행을 숨기면 복원할 수 없다."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    past_id = await _trip(client, cookies, start="2025-01-01", end="2025-01-02")
    future_id = await _trip(client, cookies, start="2099-01-01", end="2099-01-02")
    await _soft_delete(client, cookies, past_id)
    await _soft_delete(client, cookies, future_id)
    trash = await client.get("/trips?trashed=true", cookies=cookies)
    assert trash.status_code == 200, trash.text
    assert {x["trip_id"] for x in trash.json()["data"]} == {past_id, future_id}


async def test_trip_patch_rechecks_trash_under_lock(
    client, verified_user, auth_cookies, session_factory
) -> None:
    """권한 확인 뒤 휴지통으로 간 여행은 PATCH가 되살리거나 고치지 못한다(공유 편집 링크 포함)."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        assert trip is not None and trip.deleted_at is None
        version = trip.version  # 권한 확인 직후 상태 — 아직 잠그지 않은 행을 들고 있다
        await _soft_delete(client, cookies, trip_id)
        with pytest.raises(TripNotFoundError):
            await update_trip(db, trip=trip, expected_version=version, patch={"title": "부활"})
        await db.rollback()
    async with session_factory() as db:
        stored = await db.get(Trip, uuid.UUID(trip_id))
        assert stored is not None and stored.title == "리뷰 회귀" and stored.deleted_at is not None


async def test_poi_writes_recheck_trash_under_trip_lock(
    client, verified_user, auth_cookies, session_factory
) -> None:
    """POI 생성·수정·정렬은 잠금 뒤 여행 삭제 여부를 다시 본다 — 휴지통 여행에 쓰기가 남지 않게."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)
    await _soft_delete(client, cookies, trip_id)
    tid = uuid.UUID(trip_id)
    async with session_factory() as db:
        with pytest.raises(TripNotFoundError):
            await create_poi(
                db,
                trip_id=tid,
                day_index=1,
                sort_order="a1",
                feature_id=None,
                feature_snapshot={"name": "늦은 장소"},
                added_by_user_id=uuid.UUID(user_id),
            )
        await db.rollback()
        with pytest.raises(PoiNotFoundError):
            await reorder_pois(
                db, trip_id=tid, moves=[(uuid.UUID(poi["attachment_id"]), "a5")], day_index=1
            )
        await db.rollback()
        stored = await db.get(TripDayPoi, uuid.UUID(poi["attachment_id"]))
        assert stored is not None
        with pytest.raises(PoiNotFoundError):
            await update_poi(
                db, poi=stored, expected_version=stored.version, patch={"user_note": "늦은 메모"}
            )
        await db.rollback()
    async with session_factory() as db:
        stored = await db.get(TripDayPoi, uuid.UUID(poi["attachment_id"]))
        assert stored is not None and stored.sort_order == "a0" and stored.user_note is None


async def test_day_note_is_bounded(client, verified_user, auth_cookies) -> None:
    """일자 메모는 공유 페이지에도 그대로 보인다 — 댓글과 같은 2,000자 상한."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    too_long = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"note": "가" * 2001},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert too_long.status_code == 422, too_long.text
    fits = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"note": "가" * 2000},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert fits.status_code == 200, fits.text
