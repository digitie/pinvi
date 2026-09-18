"""단건 `GET /features/{id}/weather` — `kor-travel-weather` location 축(ADR-068, T-362/T-365).

`get_feature`로 좌표를 얻고 `weather_location_resolver.resolve_weather_location`
→ `latest`/`forecast`로 카드를 조립한다(구 `kor-travel-map` 날짜별 경로는 T-365에서
제거됐다).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.clients.kor_travel_map import get_kor_travel_map_client
from app.clients.kor_travel_weather import (
    CoordinateRequestOut,
    KorTravelWeatherNotFound,
    LocationOut,
    MeasurementPointOut,
    ResolvedWeatherOut,
    WeatherValueOut,
    get_optional_kor_travel_weather_client,
)
from app.main import app

pytestmark = pytest.mark.asyncio

_FEATURE_LAT, _FEATURE_LON = 37.5665, 126.978


class _FakeMapClient:
    """`get_feature`만 구현 — 좌표를 얻는 데 쓴다."""

    def __init__(self, *, feature_id: str, lon: float | None, lat: float | None) -> None:
        self.feature_id = feature_id
        self.lon = lon
        self.lat = lat
        self.calls: dict[str, Any] = {}

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        self.calls["get"] = {"feature_id": feature_id}
        if feature_id != self.feature_id:
            return None
        return {"feature_id": feature_id, "kind": "place", "lon": self.lon, "lat": self.lat}


def _weather_value(
    *,
    location_id: str,
    metric_key: str,
    value_number: float | None = None,
    value_text: str | None = None,
    forecast_style: str = "observed",
    weather_domain: str = "weather",
    unit: str | None = "deg_c",
    provider: str = "python-kma-api",
    target_at: datetime,
    severity: str | None = None,
) -> WeatherValueOut:
    return WeatherValueOut(
        value_id=f"wv-{location_id}-{metric_key}",
        location_id=location_id,
        provider=provider,
        dataset_key="kma_short_forecast",
        weather_domain=weather_domain,
        forecast_style=forecast_style,
        metric_key=metric_key,
        target_at=target_at,
        normalization_version="kma-v1",
        collected_at=datetime.now(UTC),
        source_record_key="sr-1",
        value_number=value_number,
        value_text=value_text,
        unit=unit,
        severity=severity,
        known_at=datetime.now(UTC),
    )


class _FakeWeatherClient:
    """`resolve`/`latest`/`forecast`만 구현 — `KorTravelWeatherClient`와 같은 시그니처."""

    def __init__(
        self,
        *,
        location_id: str = "loc-1",
        no_match: bool = False,
        values_by_location: dict[str, tuple[WeatherValueOut, ...]] | None = None,
    ) -> None:
        self.location_id = location_id
        self.no_match = no_match
        self.values_by_location = values_by_location or {}
        self.calls: dict[str, list[Any]] = {"resolve": [], "latest": [], "forecast": []}

    async def resolve(
        self, *, lat: float, lon: float, radius_km: float | None = None
    ) -> ResolvedWeatherOut:
        self.calls["resolve"].append({"lat": lat, "lon": lon, "radius_km": radius_km})
        if self.no_match:
            raise KorTravelWeatherNotFound(
                "no anchor", status_code=404, code="HTTP_ERROR", detail="없음"
            )
        location = LocationOut(
            location_id=self.location_id, name="중구", latitude=lat, longitude=lon, enabled=True
        )
        return ResolvedWeatherOut(
            requested=CoordinateRequestOut(latitude=lat, longitude=lon),
            location=location,
            distance_km=0.1,
            measurement_point=MeasurementPointOut(
                provider="python-airkorea-api",
                station_name="중구",
                latitude=lat,
                longitude=lon,
                distance_km=0.1,
            ),
            source_locations=(location,),
        )

    async def latest(
        self, location_id: str, *, limit: int | None = None
    ) -> tuple[WeatherValueOut, ...]:
        self.calls["latest"].append({"location_id": location_id, "limit": limit})
        return self.values_by_location.get(location_id, ())

    async def forecast(
        self,
        location_id: str,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        dataset_key: str | None = None,
        metric_key: str | None = None,
        history: bool = False,
        limit: int | None = None,
    ) -> tuple[WeatherValueOut, ...]:
        self.calls["forecast"].append(
            {"location_id": location_id, "from_": from_, "to": to, "limit": limit}
        )
        return ()


def _override(map_client: Any, weather_client: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: map_client
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather_client


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_client, None)
    app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)


async def test_resolves_feature_coord_and_builds_card(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    now = datetime.now(UTC)
    map_client = _FakeMapClient(feature_id="f_new_1", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1", metric_key="TEMP", value_number=21.5, target_at=now
                ),
                _weather_value(
                    location_id="loc-1",
                    metric_key="HUMIDITY",
                    value_number=55.0,
                    unit="%",
                    target_at=now,
                ),
            )
        }
    )
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_new_1/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["feature_id"] == "f_new_1"
    metric_keys = {m["metric_key"] for m in data["metrics"]}
    # metric key 정규화(§3.1-(3)) — TEMP -> T1H(observed), HUMIDITY -> REH.
    assert metric_keys == {"T1H", "REH"}
    assert weather_client.calls["resolve"][0]["radius_km"] == 20.0
    assert weather_client.calls["latest"][0]["location_id"] == "loc-1"


async def test_wind_speed_kmh_is_converted_to_ms(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    now = datetime.now(UTC)
    map_client = _FakeMapClient(feature_id="f_wind", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1",
                    metric_key="WIND_SPEED",
                    value_number=36.0,
                    unit="km/h",
                    provider="openweathermap",
                    target_at=now,
                ),
            )
        }
    )
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_wind/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    metric = resp.json()["data"]["metrics"][0]
    assert metric["metric_key"] == "WSD"
    assert metric["unit"] == "m/s"
    assert metric["value_number"] == pytest.approx(10.0)


async def test_unmappable_metric_passes_through_unchanged(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """CLOUD_COVER처럼 척도가 다른 metric은 원래 키로 통과한다(잘못된 값보다 미인식이 안전)."""
    user_id, _email = verified_user
    now = datetime.now(UTC)
    map_client = _FakeMapClient(feature_id="f_cloud", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1",
                    metric_key="CLOUD_COVER",
                    value_number=80.0,
                    unit="%",
                    provider="openweathermap",
                    target_at=now,
                ),
            )
        }
    )
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_cloud/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    metric = resp.json()["data"]["metrics"][0]
    assert metric["metric_key"] == "CLOUD_COVER"  # 미인식 — 원본 그대로
    assert metric["value_number"] == 80.0


async def test_weather_alert_becomes_advisory(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    now = datetime.now(UTC)
    map_client = _FakeMapClient(feature_id="f_alert", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1",
                    metric_key="ALERT",
                    value_text="강풍주의보",
                    weather_domain="weather_alert",
                    forecast_style="observed",
                    severity="watch",
                    unit=None,
                    target_at=now,
                ),
            )
        }
    )
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_alert/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    metric = resp.json()["data"]["metrics"][0]
    assert metric["forecast_style"] == "advisory"
    assert metric["severity"] == "watch"


async def test_no_anchor_within_radius_returns_empty_card(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    map_client = _FakeMapClient(feature_id="f_no_anchor", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(no_match=True)
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_no_anchor/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["metrics"] == []
    # 반경 20 -> 50 -> 100 전부 시도했다.
    assert [c["radius_km"] for c in weather_client.calls["resolve"]] == [20.0, 50.0, 100.0]


async def test_feature_without_coord_returns_empty_card(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    map_client = _FakeMapClient(feature_id="f_no_coord", lon=None, lat=None)
    weather_client = _FakeWeatherClient()
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_no_coord/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["metrics"] == []
    assert weather_client.calls["resolve"] == []  # 좌표가 없으면 해석 자체를 시도하지 않는다


async def test_past_asof_beyond_retention_returns_empty_card(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """대상 서비스 보존 지평 밖 `asof`는 no_data다(설계 §3.1-(1))."""
    user_id, _email = verified_user
    map_client = _FakeMapClient(feature_id="f_past_asof", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1",
                    metric_key="TEMP",
                    value_number=10.0,
                    target_at=datetime.now(UTC) - timedelta(days=10),
                ),
            )
        }
    )
    _override(map_client, weather_client)
    past = datetime.now(UTC) - timedelta(days=10)
    try:
        resp = await client.get(
            "/features/f_past_asof/weather",
            params={"asof": past.isoformat()},
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["metrics"] == []
    # 과거로 판정되면 location 해석 자체를 시도하지 않는다(§3.1-(1)).
    assert weather_client.calls["resolve"] == []


async def test_feature_not_found_returns_404(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    map_client = _FakeMapClient(feature_id="f_exists", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    weather_client = _FakeWeatherClient()
    _override(map_client, weather_client)
    try:
        resp = await client.get("/features/f_missing/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 404, resp.text


async def test_weather_client_unavailable_returns_503(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """T-365 — weather_client가 없으면(설정 오류) 503으로 degrade한다."""
    user_id, _email = verified_user
    map_client = _FakeMapClient(feature_id="f_no_client", lon=_FEATURE_LON, lat=_FEATURE_LAT)
    _override(map_client, None)
    try:
        resp = await client.get("/features/f_no_client/weather", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"
