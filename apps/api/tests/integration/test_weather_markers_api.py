"""`GET /weather/markers-in-bounds` — 지도 weather marker, kor-travel-weather 직접 조회
(T-368, ADR-068).

`kor-travel-map`을 전혀 참조하지 않는다 — fake client는 `KorTravelWeatherClient`의
`nearby` 시그니처만 구현한다. flag가 꺼져 있으면(기본값) 항상 빈 목록을 돌려준다는
것 자체가 "지금 운영 중인 지도와 관측상 동일"을 보장하는 핵심 단언이다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.clients.kor_travel_weather import (
    NearbyOut,
    WeatherValueOut,
    get_optional_kor_travel_weather_client,
)
from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio

_BBOX = "126.9,37.4,127.1,37.6"


def _weather_value(
    *,
    location_id: str,
    metric_key: str,
    value_number: float | None,
    provider: str = "python-kma-api",
) -> WeatherValueOut:
    now = datetime.now(UTC)
    return WeatherValueOut(
        value_id=f"wv-{location_id}-{metric_key}",
        location_id=location_id,
        provider=provider,
        dataset_key="kma_short_forecast",
        weather_domain="forecast",
        forecast_style="short",
        metric_key=metric_key,
        target_at=now,
        normalization_version="kma-v1",
        collected_at=now,
        source_record_key="sr-1",
        value_number=value_number,
        unit="deg_c",
        known_at=now,
    )


class _FakeWeatherClient:
    """`nearby`만 구현 — `KorTravelWeatherClient`와 같은 시그니처."""

    def __init__(self, result: tuple[NearbyOut, ...] = ()) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def nearby(
        self, *, lat: float, lon: float, radius_km: float, limit: int
    ) -> tuple[NearbyOut, ...]:
        self.calls.append({"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit})
        return self.result


def _override(weather_client: Any) -> None:
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather_client


def _clear() -> None:
    app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)


@pytest.fixture(autouse=True)
def _reset_flag() -> Any:
    original = settings.pinvi_kor_travel_weather_map_markers_enabled
    yield
    settings.pinvi_kor_travel_weather_map_markers_enabled = original


async def test_flag_off_returns_empty_without_calling_client(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    settings.pinvi_kor_travel_weather_map_markers_enabled = False
    weather_client = _FakeWeatherClient()
    _override(weather_client)
    try:
        resp = await client.get(
            f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["zoom"] == 10
    assert weather_client.calls == []


async def test_flag_on_returns_markers_with_temperature(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    nearby_item = NearbyOut(
        location_id="loc-1",
        name="중구",
        latitude=37.5,
        longitude=127.0,
        enabled=True,
        distance_km=1.0,
        latest=(_weather_value(location_id="loc-1", metric_key="TEMP", value_number=23.5),),
    )
    weather_client = _FakeWeatherClient(result=(nearby_item,))
    _override(weather_client)
    try:
        resp = await client.get(
            f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10&limit=30",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data["items"]) == 1
    marker = data["items"][0]
    assert marker["location_id"] == "loc-1"
    assert marker["temperature_c"] == 23.5
    assert marker["condition"] == "cloudy"
    assert marker["coord"] == {"lon": 127.0, "lat": 37.5}
    assert len(weather_client.calls) == 1
    assert weather_client.calls[0]["limit"] == 30


async def test_flag_on_zoom_below_threshold_returns_empty_without_calling_nearby(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    weather_client = _FakeWeatherClient()
    _override(weather_client)
    try:
        resp = await client.get(
            f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=5",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []
    assert weather_client.calls == []


async def test_flag_on_without_weather_client_returns_503(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    _override(None)
    try:
        resp = await client.get(
            f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"


async def test_invalid_bbox_returns_400(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    resp = await client.get(
        "/weather/markers-in-bounds?bbox=not-a-bbox&zoom=10",
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_zoom_out_of_range_returns_422(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    resp = await client.get(
        f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=3",
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 422
