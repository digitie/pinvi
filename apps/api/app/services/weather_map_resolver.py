"""`feature_id` → weather location 집합 해석의 Map 경로 (PinVi ADR-077, Map ADR-114 W7).

직접 경로(`weather_location_resolver.resolve_weather_location`)와 **같은 캐시 표**(`weather_location_links`)에 쓰지만
서로의 행은 쓰지 않는다 — Map 경로 행은 `measurement_point.resolved_via = "kor_travel_map"` 표식을 단다
(`written_by_map`). 플래그를 끄면 직접 경로가 그 행을 다시 해석해 덮어쓴다.

**위치 집합 — 직접 `/resolve`와 같은 의미 + 부분별 source.** kor-travel-weather `/resolve`는 가장 가까운 **측정소**
(AirKorea·KHOA·KREX — `measurement_point` 메타가 있는 위치)를 대표로 고르고, 거리 `max(5 km, d + 5 km)` 안의 **측정소가
아닌** 위치(KMA 격자·외부 provider 앵커)를 함께 묶는다. Map 위치에는 메타가 없어서 측정소 여부를 weather의 location_id
접두어(`airkorea-`·`khoa-`·`krex-`, weather `providers/*.py`가 만든다)로 가린다. 그 집합을 Map `GET /locations?near=`
(가까운 순)로 같은 규칙으로 고르고, 거기에 Map `GET /nearest`가 부분마다 고른 source 위치를 더한다 — 직접 경로 집합의
상위 집합이다(대표 측정소의 미세먼지가 빠지지 않고, 예보 없는 측정소 옆의 KMA 격자 예보도 빠지지 않는다).

**재해석 규칙(캐시):**

- 좌표가 바뀌었거나 `resolved_at`이 `CACHE_TTL` 넘게 지났으면 다시 해석한다 — 해석 때 없던 source가 영영 빠지지 않게.
- 핵심 부분(`current`·`forecasts.ultra_short`·`forecasts.short`)이 `not_loaded`·`unavailable`이면 그 부분의 source를 모르므로
  행을 `stale=True`로 쓴다. stale 행도 `STALE_RETRY` 동안은 그대로 쓰고(그 사이엔 Map을 다시 부르지 않는다) 그 뒤에 다시
  해석한다 — 적재 전 데이터셋 하나가 요청마다 재해석 폭주를 만들지 않게. 다른 부분(중기·외부·요약)의 실패는 stale로 치지
  않는다(TTL이 거둔다).
- 반경 안에 위치가 없으면(`/nearest` 404, 20 → 50 → 100 km) `WeatherLocationNoData`이고 행을 쓰지 않는다.

**동시성:** 네트워크(해석)는 `resolve_many_via_map`이 상한 있는 동시성으로 돌리고 DB 쓰기는 한 세션에서 순차로 한다
(`AsyncSession`은 동시 사용 금지). 쓰기는 upsert라 같은 feature의 첫 해석이 동시에 와도 충돌하지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError, KorTravelMapFeatureNotFound
from app.clients.kor_travel_map_weather import (
    MAX_LIST_LIMIT,
    KorTravelMapWeatherClient,
    WeatherForecastStyle,
    WeatherSection,
)
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_location_resolver import (
    _RESOLVE_RADII_KM,
    MAP_RESOLVED_VIA,
    WeatherLocationFound,
    WeatherLocationNoData,
    WeatherLocationResolution,
    persist_link,
    written_by_map,
)
from app.services.weather_map_state import (
    FAILED_SECTION_STATUSES,
    MapWeatherBundle,
    parse_bundle,
    parse_location_list,
)

logger = logging.getLogger(__name__)

#: 이 나이를 넘은 행은 다시 해석한다.
CACHE_TTL: Final = timedelta(days=7)
#: stale 행을 다시 해석하기까지 기다리는 시간(그 사이엔 stale 값을 쓴다).
STALE_RETRY: Final = timedelta(minutes=15)
#: trip view가 해석(네트워크)을 동시에 몇 개까지 돌리는지.
RESOLVE_CONCURRENCY: Final = 4

#: 해석이 source를 고르는 부분 — 카드·trip이 읽는 부분과 같다(Map 기본값에 기대지 않고 명시).
RESOLVER_SECTIONS: Final[tuple[WeatherSection, ...]] = ("current", "forecasts", "daily_summaries")
RESOLVER_FORECAST_STYLES: Final[tuple[WeatherForecastStyle, ...]] = (
    "ultra_short",
    "short",
    "mid",
    "external",
)
#: 이 부분의 실패만 stale로 친다(나머지는 TTL이 거둔다).
_CORE_FORECAST_STYLES: Final = ("ultra_short", "short")

#: weather가 `measurement_point` 메타를 붙이는 provider의 location_id 접두어(`providers/{airkorea,khoa,krex}.py`).
STATION_LOCATION_PREFIXES: Final = ("airkorea-", "khoa-", "krex-")
#: 대표 측정소 주변 source 반경 — weather `/resolve`의 `max(5.0, distance + 5.0)` km.
_SOURCE_RADIUS_FLOOR_M: Final = 5_000.0
_SOURCE_RADIUS_MARGIN_M: Final = 5_000.0


def is_station(location_id: str) -> bool:
    return location_id.startswith(STATION_LOCATION_PREFIXES)


@dataclass(frozen=True, slots=True)
class MapResolved:
    """해석 결과(네트워크만, 아직 쓰지 않음)."""

    location_id: str
    source_location_ids: tuple[str, ...]
    distance_km: float
    stale: bool


def core_section_failed(bundle: MapWeatherBundle) -> bool:
    sections: list[Any] = [bundle.current]
    sections += [getattr(bundle.forecasts, style) for style in _CORE_FORECAST_STYLES]
    return any(s is not None and s.status in FAILED_SECTION_STATUSES for s in sections)


def cache_hit(
    row: WeatherLocationLink | None, *, lat: float, lon: float, now: datetime
) -> WeatherLocationFound | None:
    """Map 경로 캐시 적중 판정(모듈 docstring의 재해석 규칙)."""
    if row is None or not written_by_map(row) or row.lat != lat or row.lon != lon:
        return None
    age = now - row.resolved_at
    if age > CACHE_TTL or (row.stale and age >= STALE_RETRY):
        return None
    return WeatherLocationFound(row.location_id, tuple(row.source_location_ids))


async def nearest_location_set(
    client: KorTravelMapWeatherClient,
    *,
    lat: float,
    lon: float,
    radii_km: Sequence[float] = _RESOLVE_RADII_KM,
) -> MapResolved | None:
    """좌표 → 위치 집합(Map 호출 두 번: `/nearest` + `/locations?near=`). 반경 안에 없으면 `None`."""
    bundle: MapWeatherBundle | None = None
    radius_m = 0.0
    for radius_km in radii_km:
        radius_m = radius_km * 1000.0
        try:
            data = await client.nearest(
                lon=lon,
                lat=lat,
                radius_m=radius_m,
                sections=RESOLVER_SECTIONS,
                forecast_styles=RESOLVER_FORECAST_STYLES,
            )
        except KorTravelMapFeatureNotFound:
            continue
        bundle = parse_bundle(data)
        break
    if bundle is None:
        return None

    listing = parse_location_list(
        await client.list_locations(near=(lon, lat, radius_m), limit=MAX_LIST_LIMIT)
    )
    candidates = [
        (item.location_id, float(item.distance_m))
        for item in listing.items
        if item.distance_m is not None
    ]
    nearest_distance = bundle.location.distance_m
    if not candidates:
        candidates = [
            (
                bundle.location.location_id,
                float(nearest_distance) if nearest_distance is not None else 0.0,
            )
        ]
    stations = [c for c in candidates if is_station(c[0])]
    anchor_id, anchor_distance = (stations or candidates)[0]
    source_radius = max(_SOURCE_RADIUS_FLOOR_M, anchor_distance + _SOURCE_RADIUS_MARGIN_M)
    ids = [anchor_id]
    ids += [
        location_id
        for location_id, distance in candidates
        if location_id != anchor_id and distance <= source_radius and not is_station(location_id)
    ]
    ids += bundle.section_location_ids()
    return MapResolved(
        location_id=anchor_id,
        source_location_ids=tuple(dict.fromkeys(ids)),
        distance_km=anchor_distance / 1000.0,
        stale=core_section_failed(bundle),
    )


async def _persist(
    db: AsyncSession,
    row: WeatherLocationLink | None,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    resolved: MapResolved,
    now: datetime,
) -> WeatherLocationFound:
    return await persist_link(
        db,
        row,
        feature_id=feature_id,
        lat=lat,
        lon=lon,
        location_id=resolved.location_id,
        ids=resolved.source_location_ids,
        distance_km=resolved.distance_km,
        measurement_point={"resolved_via": MAP_RESOLVED_VIA},
        stale=resolved.stale,
        now=now,
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
    """한 feature 해석(캐시 우선). Map 장애·계약 위반은 `KorTravelMapError`로 올린다(호출자가 강등한다)."""
    now = datetime.now(UTC)
    row = await db.get(WeatherLocationLink, feature_id)
    hit = cache_hit(row, lat=lat, lon=lon, now=now)
    if hit is not None:
        return hit
    resolved = await nearest_location_set(client, lat=lat, lon=lon, radii_km=radii_km)
    if resolved is None:
        logger.info(
            "weather_map_resolver.no_data",
            extra={"feature_id": feature_id, "max_radius_km": radii_km[-1] if radii_km else None},
        )
        return WeatherLocationNoData()
    return await _persist(
        db, row, feature_id=feature_id, lat=lat, lon=lon, resolved=resolved, now=now
    )


async def resolve_many_via_map(
    db: AsyncSession,
    coords: Mapping[str, tuple[float, float]],
    *,
    client: KorTravelMapWeatherClient,
    concurrency: int = RESOLVE_CONCURRENCY,
) -> dict[str, WeatherLocationResolution | KorTravelMapError]:
    """여러 feature(`feature_id → (lat, lon)`)를 한 번에 해석한다. 실패는 feature별 예외 값으로 돌려준다.

    캐시는 한 쿼리로 읽고, 미스만 상한 있는 동시성으로 Map에 묻고, 쓰기는 순차(upsert)다. 호출자의 바깥 예산
    (`asyncio.timeout`)이 끊으면 아직 쓰지 않은 결과는 버려진다.
    """
    now = datetime.now(UTC)
    rows: dict[str, WeatherLocationLink] = {}
    if coords:
        result = await db.execute(
            select(WeatherLocationLink).where(WeatherLocationLink.feature_id.in_(list(coords)))
        )
        rows = {row.feature_id: row for row in result.scalars()}

    out: dict[str, WeatherLocationResolution | KorTravelMapError] = {}
    misses: list[str] = []
    for feature_id, (lat, lon) in coords.items():
        hit = cache_hit(rows.get(feature_id), lat=lat, lon=lon, now=now)
        if hit is not None:
            out[feature_id] = hit
        else:
            misses.append(feature_id)

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def network(feature_id: str) -> MapResolved | KorTravelMapError | None:
        lat, lon = coords[feature_id]
        async with semaphore:
            try:
                return await nearest_location_set(client, lat=lat, lon=lon)
            except KorTravelMapError as exc:
                return exc

    resolved_list = await asyncio.gather(*(network(fid) for fid in misses))
    for feature_id, resolved in zip(misses, resolved_list, strict=True):
        if isinstance(resolved, KorTravelMapError):
            out[feature_id] = resolved
        elif resolved is None:
            out[feature_id] = WeatherLocationNoData()
        else:
            lat, lon = coords[feature_id]
            out[feature_id] = await _persist(
                db,
                rows.get(feature_id),
                feature_id=feature_id,
                lat=lat,
                lon=lon,
                resolved=resolved,
                now=now,
            )
    return out
