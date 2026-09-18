"""지도 weather marker 빌더 단위 테스트 (T-368, ADR-068).

`kor-travel-map`을 전혀 참조하지 않는다 — 이 경로가 T-363과 같은 "완전 분리"
원칙을 따른다는 것 자체가 테스트 대상이다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.clients.kor_travel_weather import NearbyOut, WeatherValueOut
from app.schemas.feature import BBox
from app.services.weather_map_markers import (
    MIN_WEATHER_MARKER_ZOOM,
    _derive_condition,
    _haversine_km,
    _pick_temperature,
    bbox_to_center_radius_km,
    build_weather_markers_in_bounds,
)


def _weather_value(
    *,
    location_id: str = "loc-1",
    metric_key: str,
    value_number: float | None,
    forecast_style: str = "short",
    provider: str = "python-kma-api",
    unit: str | None = "deg_c",
    known_at: datetime | None = None,
) -> WeatherValueOut:
    return WeatherValueOut(
        value_id=f"wv-{location_id}-{metric_key}",
        location_id=location_id,
        provider=provider,
        dataset_key="kma_short_forecast",
        weather_domain="forecast",
        forecast_style=forecast_style,
        metric_key=metric_key,
        target_at=datetime(2026, 9, 18, 12, tzinfo=UTC),
        normalization_version="kma-v1",
        collected_at=datetime(2026, 9, 18, 0, tzinfo=UTC),
        source_record_key="sr-1",
        value_number=value_number,
        unit=unit,
        known_at=known_at or datetime(2026, 9, 18, 0, tzinfo=UTC),
    )


def _nearby(
    *,
    location_id: str = "loc-1",
    name: str = "테스트 지점",
    latitude: float = 37.5,
    longitude: float = 127.0,
    latest: tuple[WeatherValueOut, ...] = (),
) -> NearbyOut:
    return NearbyOut(
        location_id=location_id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        enabled=True,
        distance_km=1.0,
        latest=latest,
    )


class _FakeWeatherClient:
    def __init__(self, result: tuple[NearbyOut, ...] = ()) -> None:
        self.result = result
        self.calls: list[dict[str, float | int]] = []

    async def nearby(
        self, *, lat: float, lon: float, radius_km: float, limit: int
    ) -> tuple[NearbyOut, ...]:
        self.calls.append({"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit})
        return self.result


# ── bbox_to_center_radius_km ────────────────────────────────────────────────


def test_bbox_to_center_radius_km_computes_arithmetic_mean_center() -> None:
    bbox = BBox(lng_min=126.9, lat_min=37.4, lng_max=127.1, lat_max=37.6)

    center_lat, center_lon, radius_km = bbox_to_center_radius_km(bbox)

    assert center_lat == pytest.approx(37.5)
    assert center_lon == pytest.approx(127.0)
    # 네 모서리 중 최댓값과 일치해야 한다(한 모서리만 보지 않는다).
    expected = max(
        _haversine_km(center_lat, center_lon, lat, lon)
        for lat, lon in ((37.4, 126.9), (37.4, 127.1), (37.6, 126.9), (37.6, 127.1))
    )
    assert radius_km == pytest.approx(expected)
    assert radius_km > 0


def test_bbox_to_center_radius_km_larger_bbox_yields_larger_radius() -> None:
    small = BBox(lng_min=126.99, lat_min=37.49, lng_max=127.01, lat_max=37.51)
    large = BBox(lng_min=126.5, lat_min=37.0, lng_max=127.5, lat_max=38.0)

    _, _, small_radius = bbox_to_center_radius_km(small)
    _, _, large_radius = bbox_to_center_radius_km(large)

    assert large_radius > small_radius


# ── _pick_temperature ───────────────────────────────────────────────────────


def test_pick_temperature_returns_none_without_temp_metric() -> None:
    values = [_weather_value(metric_key="PRECIP", value_number=0.0)]

    assert _pick_temperature(values) is None


def test_pick_temperature_extracts_normalized_value_and_provider() -> None:
    values = [_weather_value(metric_key="TEMP", value_number=21.5, provider="openweathermap")]

    result = _pick_temperature(values)

    assert result == (21.5, "openweathermap")


def test_pick_temperature_prefers_most_recently_known_reading() -> None:
    older = _weather_value(
        metric_key="TEMP",
        value_number=10.0,
        provider="python-kma-api",
        known_at=datetime(2026, 9, 18, 0, tzinfo=UTC),
    )
    newer = _weather_value(
        metric_key="TEMP",
        value_number=15.0,
        provider="openweathermap",
        known_at=datetime(2026, 9, 18, 6, tzinfo=UTC),
    )

    result = _pick_temperature([older, newer])

    assert result == (15.0, "openweathermap")


# ── _derive_condition ────────────────────────────────────────────────────────


def test_derive_condition_defaults_to_cloudy_without_precip_signal() -> None:
    values = [_weather_value(metric_key="TEMP", value_number=20.0)]

    assert _derive_condition(values, temperature_c=20.0) == "cloudy"


def test_derive_condition_rainy_when_precip_positive_and_warm() -> None:
    values = [_weather_value(metric_key="PRECIP", value_number=2.0, forecast_style="ultra_short")]

    assert _derive_condition(values, temperature_c=15.0) == "rainy"


def test_derive_condition_snowy_when_precip_positive_and_freezing() -> None:
    values = [_weather_value(metric_key="PRECIP", value_number=2.0, forecast_style="ultra_short")]

    assert _derive_condition(values, temperature_c=-1.0) == "snowy"


def test_derive_condition_ignores_zero_precip() -> None:
    values = [_weather_value(metric_key="PRECIP", value_number=0.0, forecast_style="ultra_short")]

    assert _derive_condition(values, temperature_c=-5.0) == "cloudy"


def test_derive_condition_never_claims_sunny() -> None:
    """맑음을 근거 없이 단정하지 않는다는 설계 원칙 자체를 고정한다."""

    values = [_weather_value(metric_key="TEMP", value_number=25.0)]

    assert _derive_condition(values, temperature_c=25.0) != "sunny"


# ── build_weather_markers_in_bounds ─────────────────────────────────────────


def _seoul_bbox() -> BBox:
    return BBox(lng_min=126.9, lat_min=37.4, lng_max=127.1, lat_max=37.6)


@pytest.mark.asyncio
async def test_build_returns_empty_below_min_zoom_without_calling_client() -> None:
    client = _FakeWeatherClient()

    markers = await build_weather_markers_in_bounds(
        bbox=_seoul_bbox(), zoom=MIN_WEATHER_MARKER_ZOOM - 1, limit=100, weather_client=client
    )

    assert markers == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_build_calls_nearby_with_center_radius_at_or_above_min_zoom() -> None:
    client = _FakeWeatherClient(
        result=(_nearby(latest=(_weather_value(metric_key="TEMP", value_number=22.0),)),)
    )

    markers = await build_weather_markers_in_bounds(
        bbox=_seoul_bbox(), zoom=MIN_WEATHER_MARKER_ZOOM, limit=50, weather_client=client
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["lat"] == pytest.approx(37.5)
    assert call["lon"] == pytest.approx(127.0)
    assert call["limit"] == 50
    assert len(markers) == 1
    assert markers[0].location_id == "loc-1"
    assert markers[0].temperature_c == 22.0
    assert markers[0].condition == "cloudy"


@pytest.mark.asyncio
async def test_build_skips_locations_without_temperature_data() -> None:
    client = _FakeWeatherClient(
        result=(
            _nearby(
                location_id="no-temp",
                latest=(
                    _weather_value(location_id="no-temp", metric_key="PRECIP", value_number=0.0),
                ),
            ),
            _nearby(
                location_id="has-temp",
                latest=(
                    _weather_value(location_id="has-temp", metric_key="TEMP", value_number=18.0),
                ),
            ),
        )
    )

    markers = await build_weather_markers_in_bounds(
        bbox=_seoul_bbox(), zoom=10, limit=100, weather_client=client
    )

    assert [m.location_id for m in markers] == ["has-temp"]


@pytest.mark.asyncio
async def test_build_skips_one_out_of_range_coord_without_failing_whole_batch() -> None:
    """`kor-travel-weather`가 한반도 유효 범위 밖 좌표를 하나 섞어 보내도(국경 부근
    location 등) 그 한 건만 빠지고 나머지 마커는 정상 반환돼야 한다 — 방어적
    per-item catch가 없으면 `Coord`의 range validator가 `ValidationError`를 던져
    전체 응답이 500으로 죽는다(적대적 리뷰에서 발견)."""

    client = _FakeWeatherClient(
        result=(
            _nearby(
                location_id="out-of-range",
                longitude=132.5,  # Coord.lon 상한(132.0) 초과
                latest=(
                    _weather_value(
                        location_id="out-of-range", metric_key="TEMP", value_number=10.0
                    ),
                ),
            ),
            _nearby(
                location_id="valid",
                latest=(_weather_value(location_id="valid", metric_key="TEMP", value_number=18.0),),
            ),
        )
    )

    markers = await build_weather_markers_in_bounds(
        bbox=_seoul_bbox(), zoom=10, limit=100, weather_client=client
    )

    assert [m.location_id for m in markers] == ["valid"]


@pytest.mark.asyncio
async def test_build_returns_empty_when_computed_radius_exceeds_service_max() -> None:
    # 전국 스케일 bbox — 반경이 kor-travel-weather 상한(500km)을 넘는다.
    whole_country = BBox(lng_min=124.0, lat_min=33.0, lng_max=132.0, lat_max=43.0)
    client = _FakeWeatherClient()

    markers = await build_weather_markers_in_bounds(
        bbox=whole_country, zoom=19, limit=100, weather_client=client
    )

    assert markers == []
    assert client.calls == []
