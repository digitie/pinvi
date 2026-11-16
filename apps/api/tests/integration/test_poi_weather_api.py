"""`GET /trips/{trip_id}/pois/{poi_id}/weather` — 장소 하나의 현재 날씨·예보 카드.

POI snapshot 좌표로 위치를 해석하므로 Map feature가 없는 직접 추가 장소도 날씨가 나온다. 해석 캐시
키는 feature가 있으면 feature_id, 없으면 `poi:{poi_id}`다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.clients.kor_travel_weather import get_optional_kor_travel_weather_client
from app.main import app
from app.services.weather_resolve_worker import get_weather_resolve_worker
from tests.integration.test_features_weather_cutover import (
    _background_clients,
    _close_background_resolvers,  # noqa: F401 — autouse fixture: worker 정리
    _FakeWeatherClient,
    _weather_value,
)
from tests.integration.test_pois_reorder import _make_trip

pytestmark = pytest.mark.asyncio

_LAT, _LON = 36.5397, 128.5181


def _override(weather_client: Any) -> None:
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather_client
    if weather_client is not None:
        _background_clients.append(weather_client)


def _clear() -> None:
    app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)


async def _add_poi(client: Any, cookies: Any, trip_id: str, **body: Any) -> dict[str, Any]:
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={"day_index": 1, "sort_order": "a0", **body},
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_manual_poi_weather_uses_snapshot_coord(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(
        client,
        cookies,
        trip_id,
        feature_id=None,
        source="manual",
        feature_snapshot={"name": "직접 추가", "coord": {"lon": _LON, "lat": _LAT}},
    )
    now = datetime.now(UTC)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1", metric_key="TEMP", value_number=11.3, target_at=now
                ),
            )
        }
    )
    _override(weather_client)
    url = f"/trips/{trip_id}/pois/{poi['attachment_id']}/weather"
    try:
        cold = await client.get(url, cookies=cookies)
        assert cold.status_code == 200, cold.text
        assert cold.json()["data"]["metrics"] == []
        await get_weather_resolve_worker(weather_client).drain()
        resp = await client.get(url, cookies=cookies)
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["feature_id"] == f"poi:{poi['attachment_id']}"
    assert [m["metric_key"] for m in data["metrics"]] == ["T1H"]
    assert data["metrics"][0]["value_number"] == 11.3
    resolve = weather_client.calls["resolve"][0]
    assert (resolve["lat"], resolve["lon"]) == (_LAT, _LON)


async def test_feature_poi_weather_keys_by_feature_id(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(
        client,
        cookies,
        trip_id,
        feature_id="f_poi_weather",
        feature_snapshot={"name": "하회마을", "lon": _LON, "lat": _LAT},
    )
    weather_client = _FakeWeatherClient()
    _override(weather_client)
    try:
        resp = await client.get(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}/weather", cookies=cookies
        )
    finally:
        _clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["feature_id"] == "f_poi_weather"


async def test_poi_without_coord_returns_empty_card_without_lookup(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_no_coord")
    weather_client = _FakeWeatherClient()
    _override(weather_client)
    try:
        resp = await client.get(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}/weather", cookies=cookies
        )
    finally:
        _clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["metrics"] == []
    assert weather_client.calls["resolve"] == []


async def test_poi_weather_requires_trip_membership_and_live_poi(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_member")
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
    _override(_FakeWeatherClient())
    try:
        url = f"/trips/{trip_id}/pois/{poi['attachment_id']}/weather"
        forbidden = await client.get(url, cookies=auth_cookies(str(stranger.user_id)))
        missing = await client.get(f"/trips/{trip_id}/pois/{uuid.uuid4()}/weather", cookies=cookies)
        deleted = await client.delete(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}", cookies=cookies
        )
        assert deleted.status_code == 204
        after_delete = await client.get(url, cookies=cookies)
    finally:
        _clear()
    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert after_delete.status_code == 404


async def test_poi_weather_503_without_weather_source(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id="f_503")
    _override(None)
    try:
        resp = await client.get(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}/weather", cookies=cookies
        )
    finally:
        _clear()
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"
