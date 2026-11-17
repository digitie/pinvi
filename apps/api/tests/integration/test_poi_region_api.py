"""장소 시도 역지오코딩 — 장소 추가 뒤 배경 조회, 장애 시 비워 두기, 백필, 좌표 이동."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_geo import KorTravelGeoUnavailable
from app.commands.poi_region_backfill import backfill_poi_regions
from app.core.time import kst_now
from app.models.poi import TripDayPoi

pytestmark = pytest.mark.asyncio

GANGNEUNG = {"lon": 128.9, "lat": 37.8}
BUSAN = {"lon": 129.16, "lat": 35.16}


class FakeGeo:
    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls = 0

    async def reverse(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _found(sig_cd: str, sido: str) -> dict[str, Any]:
    return {"candidates": [{"region": {"sig_cd": sig_cd, "sido": sido}}]}


@pytest.fixture
def geo_state():  # type: ignore[no-untyped-def]
    from app.main import app

    previous = getattr(app.state, "kor_travel_geo_client", None)

    def _set(client: object) -> None:
        app.state.kor_travel_geo_client = client

    yield _set
    app.state.kor_travel_geo_client = previous


async def _past_trip(client, cookies) -> str:  # type: ignore[no-untyped-def]
    today = kst_now().date()
    resp = await client.post(
        "/trips",
        json={
            "title": "지역 없는 여행",
            "start_date": (today - timedelta(days=3)).isoformat(),
            "end_date": (today - timedelta(days=2)).isoformat(),
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["trip_id"])


async def _add(client, cookies, trip_id, coord, sort_order="a0", feature_id=None):  # type: ignore[no-untyped-def]
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": 1,
            "sort_order": sort_order,
            "feature_id": feature_id or f"region-{uuid.uuid4().hex[:8]}",
            "feature_snapshot": {"name": "좌표만 있는 곳", "coord": coord},
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _snapshot(session_factory, poi_id) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        value = await db.scalar(
            select(TripDayPoi.feature_snapshot).where(
                TripDayPoi.attachment_id == uuid.UUID(str(poi_id))
            )
        )
    assert isinstance(value, dict)
    return value


async def test_new_place_gets_sido_after_response(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory, geo_state
) -> None:
    geo = FakeGeo(_found("51150", "강원특별자치도"))
    geo_state(geo)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _past_trip(client, cookies)
    poi = await _add(client, cookies, trip_id, GANGNEUNG)

    snapshot = await _snapshot(session_factory, poi["attachment_id"])
    assert geo.calls == 1
    assert snapshot["geo_region"]["status"] == "found"
    assert snapshot["geo_region"]["sido_code"] == "51"
    assert snapshot["geo_region"]["sig_cd"] == "51150"
    assert snapshot["name"] == "좌표만 있는 곳"  # 기존 키는 그대로

    home = (await client.get("/users/me/home", cookies=cookies)).json()["data"]
    assert [r["name"] for r in home["regions"]] == ["강원"]
    assert home["recent_places"][0]["region_name"] == "강원"


async def test_geo_outage_leaves_region_empty_then_backfill_fills_it(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory, geo_state
) -> None:
    geo_state(FakeGeo(KorTravelGeoUnavailable("down")))
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _past_trip(client, cookies)
    poi = await _add(client, cookies, trip_id, BUSAN)
    assert "geo_region" not in await _snapshot(session_factory, poi["attachment_id"])

    dry = await backfill_poi_regions(session_factory, None, dry_run=True)
    assert dry.candidates >= 1
    assert "geo_region" not in await _snapshot(session_factory, poi["attachment_id"])

    geo = FakeGeo(_found("26350", "부산광역시"))
    report = await backfill_poi_regions(session_factory, geo, dry_run=False, rate_per_second=0)
    assert report.outcomes["found"] >= 1
    assert (await _snapshot(session_factory, poi["attachment_id"]))["geo_region"][
        "sido_code"
    ] == "26"

    # 다시 돌려도 이미 채운 장소는 묻지 않는다.
    again = FakeGeo(_found("26350", "부산광역시"))
    await backfill_poi_regions(session_factory, again, dry_run=False, rate_per_second=0)
    assert (await _snapshot(session_factory, poi["attachment_id"]))["geo_region"][
        "sido_code"
    ] == "26"


async def test_not_found_is_recorded_once(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory, geo_state
) -> None:
    geo = FakeGeo({"candidates": []})
    geo_state(geo)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _past_trip(client, cookies)
    poi = await _add(client, cookies, trip_id, {"lon": 130.5, "lat": 37.0})
    assert (await _snapshot(session_factory, poi["attachment_id"]))["geo_region"]["status"] == (
        "not_found"
    )
    calls = geo.calls
    await backfill_poi_regions(session_factory, geo, dry_run=False, rate_per_second=0)
    assert geo.calls == calls


async def test_moving_a_place_drops_the_old_sido_and_looks_up_again(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory, geo_state
) -> None:
    geo_state(FakeGeo(_found("51150", "강원특별자치도")))
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _past_trip(client, cookies)
    poi = await _add(client, cookies, trip_id, GANGNEUNG)
    stale = await _snapshot(session_factory, poi["attachment_id"])
    assert stale["geo_region"]["sido_code"] == "51"

    geo_state(FakeGeo(_found("26350", "부산광역시")))
    moved = await client.patch(
        f"/trips/{trip_id}/pois/{poi['attachment_id']}",
        json={"feature_snapshot": {**stale, "coord": BUSAN}},
        headers={"If-Match": str(poi["version"])},
        cookies=cookies,
    )
    assert moved.status_code == 200, moved.text
    assert (await _snapshot(session_factory, poi["attachment_id"]))["geo_region"][
        "sido_code"
    ] == "26"
