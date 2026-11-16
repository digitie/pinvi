"""`GET /users/me/home` — 개인 홈 집계가 실제 DB의 여행·일자·장소에서 나온다."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.time import kst_now
from tests.integration.test_pois_reorder import _add_poi
from tests.integration.test_trips_api import _create_verified_user

pytestmark = pytest.mark.asyncio


async def _trip(client, cookies, title, start, end, **extra) -> str:  # type: ignore[no-untyped-def]
    body = {"title": title, **extra}
    if start is not None:
        body |= {"start_date": start.isoformat(), "end_date": end.isoformat()}
    resp = await client.post("/trips", json=body, cookies=cookies)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["trip_id"])


async def test_home_requires_login(client) -> None:  # type: ignore[no-untyped-def]
    resp = await client.get("/users/me/home")
    assert resp.status_code == 401


async def test_home_aggregates_own_trips_only(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    today = kst_now().date()

    past = await _trip(
        client,
        cookies,
        "지난 강릉",
        today - timedelta(days=10),
        today - timedelta(days=9),
        region_hint="강릉",
    )
    await _add_poi(
        client,
        cookies,
        past,
        sort_order="a0",
        feature_id="home-f-1",
        feature_snapshot={"name": "경포해변", "coord": {"lon": 128.9, "lat": 37.8}},
    )
    await _add_poi(
        client,
        cookies,
        past,
        day_index=2,
        sort_order="a0",
        feature_id="home-f-2",
        feature_snapshot={
            "name": "불국사",
            "address": {"label": "경상북도 경주시 진현동"},
            "coord": {"lon": 129.33, "lat": 35.79},
        },
    )
    upcoming = await _trip(
        client, cookies, "다음 제주", today + timedelta(days=5), today + timedelta(days=6)
    )
    # 예정 여행의 장소는 '다녀온 장소'가 아니다.
    await _add_poi(
        client,
        cookies,
        upcoming,
        sort_order="a0",
        feature_id="home-f-3",
        feature_snapshot={"name": "성산일출봉"},
    )
    await _trip(client, cookies, "날짜 미정", None, None)

    # 휴지통 여행과 남의 여행은 세지 않는다.
    trashed = await _trip(
        client, cookies, "버린 여행", today - timedelta(days=3), today - timedelta(days=3)
    )
    deleted = await client.request(
        "DELETE", f"/trips/{trashed}", json={"mode": "soft_delete"}, cookies=cookies
    )
    assert deleted.status_code == 204, deleted.text
    other_id = await _create_verified_user(
        session_factory, f"home-other-{uuid.uuid4().hex[:8]}@pinvi.test"
    )
    await _trip(
        client,
        auth_cookies(other_id),
        "남의 여행",
        today - timedelta(days=2),
        today - timedelta(days=1),
    )

    resp = await client.get("/users/me/home", cookies=cookies)
    assert resp.status_code == 200, resp.text
    home = resp.json()["data"]
    assert home["today"] == today.isoformat()
    assert home["stats"] == {
        "trip_count": 3,
        "upcoming_trip_count": 1,
        "ongoing_trip_count": 0,
        "completed_trip_count": 1,
        "undated_trip_count": 1,
        "travel_day_count": 2,
        "visited_place_count": 2,
        "region_count": 2,
    }
    assert home["next_trip"]["trip_id"] == upcoming
    assert home["next_trip"]["days_until"] == 5
    assert home["next_trip"]["place_count"] == 1
    assert [t["title"] for t in home["upcoming_trips"]] == ["날짜 미정"]
    assert [t["title"] for t in home["recent_trips"]] == ["지난 강릉"]
    assert home["recent_trips"][0]["region_name"] == "강원"
    assert [(p["name"], p["region_name"]) for p in home["recent_places"]] == [
        ("불국사", "경북"),
        ("경포해변", "강원"),
    ]
    assert sorted(r["name"] for r in home["regions"]) == ["강원", "경북"]


async def test_home_empty_user(client, verified_user, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    resp = await client.get("/users/me/home", cookies=auth_cookies(user_id))
    assert resp.status_code == 200, resp.text
    home = resp.json()["data"]
    assert home["next_trip"] is None
    assert home["stats"]["trip_count"] == 0
    assert home["recent_places"] == [] and home["regions"] == []
