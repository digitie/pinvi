"""`feature_id` ↔ `kor-travel-weather` `location_id` 해석 + 캐시 (T-361/P2, ADR-068).

`kor-travel-weather`의 `/v1/weather/resolve`는 1회 호출에 3.1 MB급 응답이라 조회
경로에서 매번 부를 수 없다 — `app.weather_location_links`에 결과를 캐시하고, 좌표가
바뀌지 않는 한 재사용한다.

**반경 확대**: 20 → 50 → 100 km. 각 반경에서 `KorTravelWeatherNotFound`(해당 서비스는
반경 내 앵커가 없으면 404를 준다 — OpenAPI 스키마에는 선언되지 않았지만 실측으로
확인된 실제 동작)를 받으면 다음 반경으로 넘어간다. 세 반경 모두 실패하면 **장애가
아니라 `WeatherLocationNoData`**다.

**`source_location_ids` 전체 저장**: `/resolve`의 대표 `location` 하나만 저장하면
기상청 예보가 조용히 누락된다(설계 문서 §3.3 — 서울시청 실측에서 대표 location은
AirKorea 측정소였고 KMA 예보는 다른 source location에 있었다). `resolved.location`이
`resolved.source_locations`에 이미 포함되는 경우가 실측상 일반적이지만, 비어 있는
방어적 상황에도 대표 location_id를 항상 포함하도록 순서를 보존한 채 dedupe한다.

**coordinate 변경 처리**: 캐시된 좌표와 다르면 먼저 `stale=True`를 커밋해 둔 뒤
재해석한다 — 재해석 도중 예외가 나도(네트워크 오류 등) `stale=True`만은 남아 다음
호출이 다시 시도하게 만든다(2단계 커밋, `trip_day_rise_set.py`의 stale 마킹 관례와
같은 정신이나 여기서는 동기적으로 즉시 재해석까지 한다는 점이 다르다 — weather는
요청 경로에서 지금 답이 필요하다).

**Map 경로(ADR-077)**: `PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED`가 켜지면 같은 캐시를 Map
`/v1/service/weather/nearest`로 채운다(`resolve_weather_location_via_map`).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapFeatureNotFound
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherNotFound,
    ResolvedWeatherOut,
)
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_map_state import parse_bundle

logger = logging.getLogger(__name__)

_RESOLVE_RADII_KM: tuple[float, ...] = (20.0, 50.0, 100.0)


@dataclass(frozen=True, slots=True)
class WeatherLocationFound:
    location_id: str
    source_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeatherLocationNoData:
    """반경 내 앵커 없음 — 장애가 아니다. 상한 반경(100km)까지 시도한 뒤의 결과."""


WeatherLocationResolution = WeatherLocationFound | WeatherLocationNoData


def _dedupe_preserving_order(ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ids))


def _measurement_point_dict(resolved: ResolvedWeatherOut) -> dict[str, object] | None:
    if resolved.measurement_point is None:
        return None
    return dataclasses.asdict(resolved.measurement_point)


async def _resolve_via_client(
    client: KorTravelWeatherClient, *, lat: float, lon: float, radii_km: Sequence[float]
) -> ResolvedWeatherOut | None:
    for radius_km in radii_km:
        try:
            return await client.resolve(lat=lat, lon=lon, radius_km=radius_km)
        except KorTravelWeatherNotFound:
            continue
    return None


async def _cached_or_mark_stale(
    db: AsyncSession, *, feature_id: str, lat: float, lon: float
) -> tuple[WeatherLocationLink | None, WeatherLocationFound | None]:
    """캐시 적중이면 `(row, found)`. 좌표가 바뀌었으면 재해석 전에 먼저 stale을 커밋한다."""
    row = await db.get(WeatherLocationLink, feature_id)

    if row is not None and not row.stale and row.lat == lat and row.lon == lon:
        return row, WeatherLocationFound(row.location_id, tuple(row.source_location_ids))

    if row is not None and not row.stale and (row.lat != lat or row.lon != lon):
        # 좌표 변경 — 재해석 전에 먼저 stale을 커밋해 둔다(중간에 실패해도 다음 호출이
        # 재시도하도록).
        row.stale = True
        await db.commit()
    return row, None


async def _persist(
    db: AsyncSession,
    row: WeatherLocationLink | None,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    location_id: str,
    ids: tuple[str, ...],
    distance_km: float,
    measurement_point: dict[str, object] | None,
    stale: bool = False,
) -> WeatherLocationFound:
    if row is None:
        row = WeatherLocationLink(feature_id=feature_id)
        db.add(row)
    row.location_id = location_id
    row.source_location_ids = list(ids)
    row.lat = lat
    row.lon = lon
    row.distance_km = distance_km
    row.measurement_point = measurement_point
    row.resolved_at = datetime.now(UTC)
    row.stale = stale
    await db.commit()
    return WeatherLocationFound(location_id, ids)


async def resolve_weather_location(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    client: KorTravelWeatherClient,
    radii_km: Sequence[float] = _RESOLVE_RADII_KM,
) -> WeatherLocationResolution:
    """`feature_id`의 좌표를 `kor-travel-weather` location으로 해석(캐시 우선)."""
    row, cached = await _cached_or_mark_stale(db, feature_id=feature_id, lat=lat, lon=lon)
    if cached is not None:
        return cached

    resolved = await _resolve_via_client(client, lat=lat, lon=lon, radii_km=radii_km)
    if resolved is None:
        logger.info(
            "weather_location_resolver.no_data",
            extra={"feature_id": feature_id, "max_radius_km": radii_km[-1] if radii_km else None},
        )
        return WeatherLocationNoData()

    ids = _dedupe_preserving_order(
        [resolved.location.location_id, *(loc.location_id for loc in resolved.source_locations)]
    )
    return await _persist(
        db,
        row,
        feature_id=feature_id,
        lat=lat,
        lon=lon,
        location_id=resolved.location.location_id,
        ids=ids,
        distance_km=resolved.distance_km,
        measurement_point=_measurement_point_dict(resolved),
    )


async def resolve_weather_location_via_map(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    client: KorTravelMapWeatherClient,
    radii_km: Sequence[float] = _RESOLVE_RADII_KM,
) -> WeatherLocationResolution:
    """같은 해석을 Map `GET /v1/service/weather/nearest`로 한다(ADR-077, 플래그 on일 때).

    캐시(`weather_location_links`)는 직접 경로와 **같은 표**다 — 두 경로 모두 weather `location_id`를 저장하므로
    플래그를 바꿔도 캐시가 그대로 유효하다. Map `/nearest`는 부분(관측·예보 style별·요약)마다 값이 있는 가장 가까운
    위치를 고르고 `source.location_id`로 알린다 — 대표 위치 + 부분별 source 위치를 `source_location_ids`로 저장해
    직접 경로의 "source bundle 전체" 규칙(§3.3, KMA 예보 누락 방지)을 그대로 지킨다.

    한 부분이라도 `not_loaded`·`unavailable`이면(그 부분의 source를 아직 모른다) 결과는 쓰되 행을 `stale=True`로
    남겨 다음 호출이 다시 해석하게 한다 — 적재 전에 해석한 위치가 그 부분의 위치를 영영 빠뜨리지 않게.

    Map 장애·계약 위반은 `KorTravelMapError`·`MapWeatherContractError`로 올린다(호출자가 강등한다).
    """
    row, cached = await _cached_or_mark_stale(db, feature_id=feature_id, lat=lat, lon=lon)
    if cached is not None:
        return cached

    data: dict[str, Any] | None = None
    for radius_km in radii_km:
        try:
            data = await client.nearest(lon=lon, lat=lat, radius_m=radius_km * 1000.0)
        except KorTravelMapFeatureNotFound:
            continue
        break
    if data is None:
        logger.info(
            "weather_location_resolver.no_data",
            extra={
                "feature_id": feature_id,
                "max_radius_km": radii_km[-1] if radii_km else None,
                "source": "kor_travel_map",
            },
        )
        return WeatherLocationNoData()

    bundle = parse_bundle(data)
    distance_m = bundle.location.distance_m
    return await _persist(
        db,
        row,
        feature_id=feature_id,
        lat=lat,
        lon=lon,
        location_id=bundle.location.location_id,
        ids=tuple(bundle.section_location_ids()),
        distance_km=float(distance_m) / 1000.0 if distance_m is not None else 0.0,
        measurement_point=None,
        stale=bundle.any_section_failed(),
    )
