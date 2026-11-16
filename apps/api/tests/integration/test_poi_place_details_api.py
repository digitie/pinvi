"""`/trips/{trip_id}/pois/{poi_id}/place-details` — 장소 영업 정보 저장·재조회·삭제.

- 처음 열 때 한 번 받아 저장하고 다음부터는 저장값을 준다(출처 재호출 없음).
- 장소를 지우면 행도 지워지고, 같은 곳을 다시 넣으면 다시 받는다.
- "다시 읽어오기"는 60초에 1회, 덮어쓰기, 출처 장애면 503 + 기존 값 유지, viewer 거부.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update

from app.clients.kor_travel_map import KorTravelMapUnavailable, get_optional_kor_travel_map_client
from app.main import app
from app.models.poi_place_detail import TripPoiPlaceDetail
from tests.integration.test_pois_reorder import _make_trip

pytestmark = pytest.mark.asyncio


class _FakeMapClient:
    def __init__(self, dto: dict[str, Any] | None) -> None:
        self.dto = dto
        self.calls: list[str] = []
        self.fail = False

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        self.calls.append(feature_id)
        if self.fail:
            raise KorTravelMapUnavailable("down")
        return self.dto


def _dto(phone: str = "054-853-0109") -> dict[str, Any]:
    return {
        "feature_id": "f_hahoe",
        "kind": "place",
        "detail": {
            "phones": [phone],
            "facility_info": {"operating_time": "09:00~18:00", "rstde_info": "연중무휴"},
        },
        "urls": {"homepage": "https://www.hahoe.or.kr"},
    }


def _override(map_client: Any) -> None:
    app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: map_client


def _clear() -> None:
    app.dependency_overrides.pop(get_optional_kor_travel_map_client, None)


async def _add_poi(client: Any, cookies: Any, trip_id: str, **body: Any) -> dict[str, Any]:
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={"day_index": 1, "sort_order": body.pop("sort_order", "a0"), **body},
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _row_count(session_factory: Any, poi_id: str) -> int:
    async with session_factory() as db:
        return int(
            await db.scalar(
                select(func.count())
                .select_from(TripPoiPlaceDetail)
                .where(TripPoiPlaceDetail.poi_id == uuid.UUID(poi_id))
            )
            or 0
        )


async def test_fetch_once_store_delete_and_refetch_on_readd(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_hahoe")
    map_client = _FakeMapClient(_dto())
    _override(map_client)
    url = f"/trips/{trip_id}/pois/{poi['attachment_id']}/place-details"
    try:
        first = await client.get(url, cookies=cookies)
        second = await client.get(url, cookies=cookies)
        assert map_client.calls == ["f_hahoe"]  # 두 번째는 저장값
        assert await _row_count(session_factory, poi["attachment_id"]) == 1

        deleted = await client.delete(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}", cookies=cookies
        )
        assert deleted.status_code == 204
        assert await _row_count(session_factory, poi["attachment_id"]) == 0
        gone = await client.get(url, cookies=cookies)

        readded = await _add_poi(client, cookies, trip_id, feature_id="f_hahoe", sort_order="a1")
        map_client.dto = _dto(phone="054-000-0000")
        again = await client.get(
            f"/trips/{trip_id}/pois/{readded['attachment_id']}/place-details", cookies=cookies
        )
    finally:
        _clear()

    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["status"] == "ready"
    assert data["opening_hours"] == ["09:00~18:00"]
    assert data["closed_days"] == "연중무휴"
    assert data["phone"] == "054-853-0109"
    assert data["website"] == "https://www.hahoe.or.kr"
    assert data["sources"] == {
        "opening_hours": "kor_travel_map",
        "closed_days": "kor_travel_map",
        "phone": "kor_travel_map",
        "website": "kor_travel_map",
    }
    assert data["refresh_available_at"] is not None
    assert second.json()["data"] == data
    assert gone.status_code == 404
    assert again.json()["data"]["phone"] == "054-000-0000"
    assert map_client.calls == ["f_hahoe", "f_hahoe"]


async def test_manual_poi_is_empty_without_lookup_and_outage_is_quiet(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    manual = await _add_poi(
        client,
        cookies,
        trip_id,
        feature_id=None,
        source="manual",
        feature_snapshot={"name": "직접", "coord": {"lon": 127.0, "lat": 37.5}},
    )
    linked = await _add_poi(client, cookies, trip_id, feature_id="f_down", sort_order="a1")
    map_client = _FakeMapClient(_dto())
    map_client.fail = True
    _override(map_client)
    try:
        empty = await client.get(
            f"/trips/{trip_id}/pois/{manual['attachment_id']}/place-details", cookies=cookies
        )
        down = await client.get(
            f"/trips/{trip_id}/pois/{linked['attachment_id']}/place-details", cookies=cookies
        )
    finally:
        _clear()
    assert empty.json()["data"]["status"] == "empty"
    assert map_client.calls == ["f_down"]
    assert down.status_code == 200
    assert down.json()["data"]["status"] == "unavailable"
    # 장애는 저장하지 않는다 — 다음 열람 때 다시 시도.
    assert await _row_count(session_factory, linked["attachment_id"]) == 0


async def test_refresh_rate_limit_overwrite_and_outage(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_hahoe")
    map_client = _FakeMapClient(_dto())
    _override(map_client)
    base = f"/trips/{trip_id}/pois/{poi['attachment_id']}/place-details"

    async def _age_row() -> None:
        async with session_factory() as db:
            await db.execute(
                update(TripPoiPlaceDetail)
                .where(TripPoiPlaceDetail.poi_id == uuid.UUID(poi["attachment_id"]))
                .values(fetched_at=datetime.now(UTC) - timedelta(minutes=5))
            )
            await db.commit()

    try:
        await client.get(base, cookies=cookies)
        too_soon = await client.post(f"{base}/refresh", cookies=cookies)
        await _age_row()
        map_client.dto = _dto(phone="054-111-2222")
        refreshed = await client.post(f"{base}/refresh", cookies=cookies)
        await _age_row()
        map_client.fail = True
        outage = await client.post(f"{base}/refresh", cookies=cookies)
        after_outage = await client.get(base, cookies=cookies)
    finally:
        _clear()

    assert too_soon.status_code == 429
    assert too_soon.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(too_soon.headers["Retry-After"]) <= 60
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["data"]["phone"] == "054-111-2222"
    assert outage.status_code == 503
    assert outage.json()["error"]["code"] == "PLACE_DETAILS_UNAVAILABLE"
    assert after_outage.json()["data"]["phone"] == "054-111-2222"


async def test_refresh_without_stored_row_and_permissions(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_hahoe")
    async with session_factory() as db:
        stranger = User(
            email=f"stranger_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash=None,
            nickname="남",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(stranger)
        await db.commit()
        await db.refresh(stranger)
    _override(_FakeMapClient(_dto()))
    base = f"/trips/{trip_id}/pois/{poi['attachment_id']}/place-details"
    try:
        created = await client.post(f"{base}/refresh", cookies=cookies)
        forbidden_get = await client.get(base, cookies=auth_cookies(str(stranger.user_id)))
        forbidden_refresh = await client.post(
            f"{base}/refresh", cookies=auth_cookies(str(stranger.user_id))
        )
    finally:
        _clear()
    assert created.status_code == 200, created.text
    assert created.json()["data"]["status"] == "ready"
    assert forbidden_get.status_code == 403
    assert forbidden_refresh.status_code == 403
