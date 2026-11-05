"""`weather_location_resolver` 통합 테스트 — 실제 Postgres `app.weather_location_links` (T-361/P2, ADR-068)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
import pytest_asyncio

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
    WeatherLocationPending,
    resolve_weather_location,
)
from app.services.weather_resolve_worker import (
    _WORKERS,
    close_weather_resolve_worker,
    get_weather_resolve_worker,
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
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> ResolvedWeatherOut:
        assert read_timeout_seconds == 45.0
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


@pytest_asyncio.fixture(autouse=True)
async def _close_background_workers():
    before = set(_WORKERS)
    yield
    for client in list(_WORKERS):
        if client not in before:
            await close_weather_resolve_worker(client)


async def _fill(factory, client, *, feature_id, lat, lon):
    async with factory() as db:
        first = await resolve_weather_location(
            db, feature_id=feature_id, lat=lat, lon=lon, client=client
        )
    assert isinstance(first, WeatherLocationPending)
    await get_weather_resolve_worker(client).drain()
    async with factory() as db:
        return await resolve_weather_location(
            db, feature_id=feature_id, lat=lat, lon=lon, client=client
        )


async def test_cache_miss_resolves_and_persists_all_source_locations(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=0, result=_resolved())
    result = await _fill(session_factory, client, feature_id="f1", lat=37.5665, lon=126.978)
    assert isinstance(result, WeatherLocationFound)
    assert result.source_location_ids == ("airkorea-station-abc", "e2e-seoul")
    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f1")
        assert row.location_id == "airkorea-station-abc"
        assert row.source_location_ids == ["airkorea-station-abc", "e2e-seoul"]
        assert (row.lat, row.lon, row.stale) == (37.5665, 126.978, False)
        assert row.measurement_point == dataclasses.asdict(_resolved().measurement_point)


async def test_cache_hit_skips_network_call(session_factory: Any) -> None:
    seed = _FakeClient(min_radius_km=0, result=_resolved())
    await _fill(session_factory, seed, feature_id="f2", lat=1, lon=2)
    assert seed.calls == [20.0]
    hit = _FakeClient(min_radius_km=0, result=_resolved())
    async with session_factory() as db:
        result = await resolve_weather_location(db, feature_id="f2", lat=1, lon=2, client=hit)
    assert isinstance(result, WeatherLocationFound)
    assert hit.calls == []


async def test_radius_escalates_20_then_50_then_100(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=60, result=_resolved())
    assert isinstance(
        await _fill(session_factory, client, feature_id="f3", lat=3, lon=4), WeatherLocationFound
    )
    assert client.calls == [20.0, 50.0, 100.0]


async def test_all_radii_exhausted_returns_no_data_without_writing_row(
    session_factory: Any,
) -> None:
    client = _FakeClient(min_radius_km=999, result=_resolved())
    assert isinstance(
        await _fill(session_factory, client, feature_id="f4", lat=5, lon=6), WeatherLocationNoData
    )
    assert client.calls == [20.0, 50.0, 100.0]
    async with session_factory() as db:
        assert await db.get(WeatherLocationLink, "f4") is None


async def test_coordinate_change_replaces_only_in_background(session_factory: Any) -> None:
    first = _FakeClient(min_radius_km=0, result=_resolved())
    await _fill(session_factory, first, feature_id="f5", lat=10, lon=20)
    second_result = dataclasses.replace(
        _resolved(),
        location=_SEOUL_KMA,
        requested=CoordinateRequestOut(latitude=11, longitude=21),
        measurement_point=None,
        source_locations=(_SEOUL_KMA,),
        distance_km=1,
    )
    second = _FakeClient(min_radius_km=0, result=second_result)
    found = await _fill(session_factory, second, feature_id="f5", lat=11, lon=21)
    assert found.location_id == "e2e-seoul"
    assert second.calls == [20.0]
    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f5")
        assert (row.lat, row.lon, row.stale) == (11, 21, False)
        assert row.location_id == "e2e-seoul"


async def test_stale_row_is_not_treated_as_cache_hit(session_factory: Any) -> None:
    seed = _FakeClient(min_radius_km=0, result=_resolved())
    await _fill(session_factory, seed, feature_id="f6", lat=7, lon=8)
    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, "f6")
        row.stale = True
        await db.commit()
    client = _FakeClient(min_radius_km=0, result=_resolved())
    found = await _fill(session_factory, client, feature_id="f6", lat=7, lon=8)
    assert isinstance(found, WeatherLocationFound)
    assert client.calls == [20.0]


async def test_measurement_point_none_is_persisted_as_null(session_factory: Any) -> None:
    client = _FakeClient(min_radius_km=0, result=_resolved(with_measurement_point=False))
    await _fill(session_factory, client, feature_id="f7", lat=9, lon=10)
    async with session_factory() as db:
        assert (await db.get(WeatherLocationLink, "f7")).measurement_point is None


async def test_source_locations_without_representative_still_includes_it(
    session_factory: Any,
) -> None:
    client = _FakeClient(
        min_radius_km=0, result=dataclasses.replace(_resolved(), source_locations=())
    )
    found = await _fill(session_factory, client, feature_id="f8", lat=1, lon=2)
    assert found.source_location_ids == ("airkorea-station-abc",)
