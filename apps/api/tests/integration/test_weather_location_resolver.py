"""`weather_location_resolver` 통합 테스트 — 실제 Postgres `app.weather_location_links` (T-361/P2, ADR-068)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.clients.kor_travel_weather import (
    CoordinateRequestOut,
    KorTravelWeatherNotFound,
    LocationOut,
    MeasurementPointOut,
    ResolvedWeatherOut,
)
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_location_resolver import (
    WeatherLocationFound,
    WeatherLocationNoData,
    resolve_weather_location,
)

pytestmark = pytest.mark.asyncio

_SEOUL = LocationOut(
    location_id="airkorea-station-abc",
    name="중구",
    latitude=37.5,
    longitude=126.9,
    enabled=True,
)
_SEOUL_KMA = LocationOut(
    location_id="e2e-seoul",
    name="서울 운영 테스트",
    latitude=37.566,
    longitude=126.978,
    enabled=True,
    nx=60,
    ny=127,
)


class _FakeClient:
    """min radius를 만족해야만 결과를 주는 가짜 client — 반경 확대 로직 검증용."""

    def __init__(self, *, min_radius_km: float, result: ResolvedWeatherOut) -> None:
        self.min_radius_km = min_radius_km
        self.result = result
        self.calls: list[float] = []

    async def resolve(
        self, *, lat: float, lon: float, radius_km: float | None = None
    ) -> ResolvedWeatherOut:
        self.calls.append(radius_km or 0.0)
        if (radius_km or 0.0) < self.min_radius_km:
            raise KorTravelWeatherNotFound(
                "no anchor", status_code=404, code="HTTP_ERROR", detail="없음"
            )
        return self.result


def _resolved(*, with_measurement_point: bool = True) -> ResolvedWeatherOut:
    mp = (
        MeasurementPointOut(
            provider="python-airkorea-api",
            station_name="중구",
            latitude=37.5,
            longitude=126.9,
            distance_km=0.27,
        )
        if with_measurement_point
        else None
    )
    return ResolvedWeatherOut(
        requested=CoordinateRequestOut(latitude=37.5665, longitude=126.978),
        location=_SEOUL,
        distance_km=0.27,
        measurement_point=mp,
        source_locations=(_SEOUL, _SEOUL_KMA),
        latest=(),
        forecast=(),
        alerts=(),
    )


async def test_cache_miss_resolves_and_persists_all_source_locations(
    session_factory: Any,
) -> None:
    client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f1", lat=37.5665, lon=126.978, client=client
        )
        assert isinstance(result, WeatherLocationFound)
        assert result.location_id == "airkorea-station-abc"
        # 대표 location + 나머지 source location 전체 — 번들 하나만 캐시하는 함정을 막는다.
        assert result.source_location_ids == ("airkorea-station-abc", "e2e-seoul")

    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f1")
        assert row is not None
        assert row.location_id == "airkorea-station-abc"
        assert row.source_location_ids == ["airkorea-station-abc", "e2e-seoul"]
        assert row.lat == 37.5665
        assert row.lon == 126.978
        assert row.stale is False
        assert row.measurement_point == dataclasses.asdict(_resolved().measurement_point)  # type: ignore[arg-type]


async def test_cache_hit_skips_network_call(session_factory: Any) -> None:
    seed_client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        await resolve_weather_location(db, feature_id="f2", lat=1.0, lon=2.0, client=seed_client)
    assert seed_client.calls == [20.0]

    hit_client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f2", lat=1.0, lon=2.0, client=hit_client
        )
    assert isinstance(result, WeatherLocationFound)
    assert hit_client.calls == []  # 네트워크 호출 없음 — 캐시 히트


async def test_radius_escalates_20_then_50_then_100(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=60.0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f3", lat=3.0, lon=4.0, client=client
        )
    assert isinstance(result, WeatherLocationFound)
    assert client.calls == [20.0, 50.0, 100.0]


async def test_all_radii_exhausted_returns_no_data_without_writing_row(
    session_factory: Any,
) -> None:
    client = _FakeClient(min_radius_km=999.0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f4", lat=5.0, lon=6.0, client=client
        )
    assert isinstance(result, WeatherLocationNoData)
    assert client.calls == [20.0, 50.0, 100.0]

    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f4")
        assert row is None


async def test_coordinate_change_marks_stale_before_reresolving(session_factory: Any) -> None:
    first_client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        await resolve_weather_location(db, feature_id="f5", lat=10.0, lon=20.0, client=first_client)

    # 좌표 변경 — 재해석해야 한다(캐시 히트 아님).
    moved_result = ResolvedWeatherOut(
        requested=CoordinateRequestOut(latitude=11.0, longitude=21.0),
        location=_SEOUL_KMA,
        distance_km=1.0,
        measurement_point=None,
        source_locations=(_SEOUL_KMA,),
        latest=(),
        forecast=(),
        alerts=(),
    )
    second_client = _FakeClient(min_radius_km=0.0, result=moved_result)
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f5", lat=11.0, lon=21.0, client=second_client
        )
    assert isinstance(result, WeatherLocationFound)
    assert result.location_id == "e2e-seoul"
    assert second_client.calls == [20.0]  # 재해석은 다시 20km부터 시작

    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f5")
        assert row is not None
        assert row.lat == 11.0
        assert row.lon == 21.0
        assert row.location_id == "e2e-seoul"
        assert row.stale is False  # 성공적으로 재해석했으므로 stale 해소


async def test_stale_row_is_not_treated_as_cache_hit(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        await resolve_weather_location(db, feature_id="f6", lat=7.0, lon=8.0, client=client)
        row = await db.get(WeatherLocationLink, "f6")
        assert row is not None
        row.stale = True
        await db.commit()

    refresh_client = _FakeClient(min_radius_km=0.0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f6", lat=7.0, lon=8.0, client=refresh_client
        )
    assert isinstance(result, WeatherLocationFound)
    assert refresh_client.calls == [20.0]  # stale이면 좌표가 같아도 재해석


async def test_measurement_point_none_is_persisted_as_null(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=0.0, result=_resolved(with_measurement_point=False))
    async with session_factory() as db:
        await resolve_weather_location(db, feature_id="f7", lat=9.0, lon=10.0, client=client)

    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f7")
        assert row is not None
        assert row.measurement_point is None


async def test_source_locations_without_representative_still_includes_it(
    session_factory: Any,
) -> None:
    """방어적 케이스 — `source_locations`가 대표 location을 안 담고 있어도 dedupe로 포함된다."""
    resolved = ResolvedWeatherOut(
        requested=CoordinateRequestOut(latitude=1.0, longitude=2.0),
        location=_SEOUL,
        distance_km=0.1,
        measurement_point=None,
        source_locations=(),
        latest=(),
        forecast=(),
        alerts=(),
    )
    client = _FakeClient(min_radius_km=0.0, result=resolved)
    async with session_factory() as db:
        result = await resolve_weather_location(
            db, feature_id="f8", lat=1.0, lon=2.0, client=client
        )
    assert isinstance(result, WeatherLocationFound)
    assert result.source_location_ids == ("airkorea-station-abc",)
