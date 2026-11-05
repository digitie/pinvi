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

**요청/배경 분리(#621)**: 요청은 같은 좌표의 유효한 직접 캐시만 읽는다. 미스는
즉시 `WeatherLocationPending`을 돌려주고 제한된 배경 해석을 예약한다. 배경은 요청과
다른 세션·deadline context를 쓰며, 좌표/Map 캐시 변경 전에 출발한 결과는 저장하지 않는다.
호출자의 미확정 쓰기를 commit/rollback하지 않는다.

**Map 경로(ADR-077)**: `PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED`가 켜지면 같은 표를 Map으로 채운다
(`weather_map_resolver.py`). 두 경로는 서로의 행을 캐시로 쓰지 않는다(`written_by_map`).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherNotFound,
    ResolvedWeatherOut,
)
from app.db.session import release_read_connection
from app.models.weather_location_link import WeatherLocationLink

logger = logging.getLogger(__name__)

_RESOLVE_RADII_KM: tuple[float, ...] = (20.0, 50.0, 100.0)


@dataclass(frozen=True, slots=True)
class WeatherLocationFound:
    location_id: str
    source_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeatherLocationNoData:
    """반경 내 앵커 없음 — 장애가 아니다. 상한 반경(100km)까지 시도한 뒤의 결과."""


@dataclass(frozen=True, slots=True)
class WeatherLocationPending:
    """미해석/대기/실패 — 관측소 없음을 확정하지 않았으므로 unavailable로 투영한다."""


WeatherLocationResolution = WeatherLocationFound | WeatherLocationNoData | WeatherLocationPending


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
            return await client.resolve(
                lat=lat, lon=lon, radius_km=radius_km, read_timeout_seconds=45.0
            )
        except KorTravelWeatherNotFound:
            continue
    return None


#: Map 경로(ADR-077)가 쓴 행의 표식 — `measurement_point` JSONB에 둔다(이 열을 읽는 코드는 없다, 스키마 변경 회피).
#: 직접 경로는 이 표식이 있는 행을 캐시로 쓰지 않고(플래그를 끄면 다시 해석), Map 경로는 표식 없는 행을 쓰지 않는다.
MAP_RESOLVED_VIA: Final = "kor_travel_map"


def written_by_map(row: WeatherLocationLink) -> bool:
    point = row.measurement_point
    return isinstance(point, dict) and point.get("resolved_via") == MAP_RESOLVED_VIA


async def _read_cached(
    db: AsyncSession, *, feature_id: str, lat: float, lon: float
) -> tuple[WeatherLocationLink | None, WeatherLocationFound | None]:
    """요청은 읽기만 한다. Map/stale/좌표 불일치는 별도 세션에서 재해석한다."""
    with db.no_autoflush:
        row = await db.get(WeatherLocationLink, feature_id)
    if (
        row is not None
        and not written_by_map(row)
        and not row.stale
        and row.lat == lat
        and row.lon == lon
    ):
        return row, WeatherLocationFound(row.location_id, tuple(row.source_location_ids))
    return row, None


async def persist_link(
    db: AsyncSession,
    row: WeatherLocationLink | None,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    location_id: str,
    ids: tuple[str, ...],
    distance_km: float,
    measurement_point: dict[str, Any] | None,
    stale: bool = False,
    now: datetime | None = None,
) -> WeatherLocationFound:
    """해석 결과를 **upsert**한다 — 같은 feature를 두 요청이 처음 동시에 해석해도 PK 충돌(IntegrityError)이 없다."""
    values: dict[str, Any] = {
        "location_id": location_id,
        "source_location_ids": list(ids),
        "lat": lat,
        "lon": lon,
        "distance_km": distance_km,
        "measurement_point": measurement_point,
        "resolved_at": now or datetime.now(UTC),
        "stale": stale,
    }
    statement = pg_insert(WeatherLocationLink).values(feature_id=feature_id, **values)
    statement = statement.on_conflict_do_update(
        index_elements=[WeatherLocationLink.feature_id],
        set_={**values, "updated_at": func.now()},
    )
    await db.execute(statement)
    await db.commit()
    if row is not None:
        # 같은 세션의 identity map이 옛 값을 들고 있지 않게(expire_on_commit=False).
        db.expire(row)
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
    """캐시 적중만 즉시 사용하고 미스는 별도 세션의 배경 해석으로 예약한다."""
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    row, cached = await _read_cached(db, feature_id=feature_id, lat=lat, lon=lon)
    if cached is not None:
        return cached
    # ORM 쓰기가 있으면 release helper는 아무것도 하지 않는다. 호출자 transaction은 보존한다.
    await release_read_connection(db)
    return get_weather_resolve_worker(client).schedule(
        feature_id=feature_id, lat=lat, lon=lon, radii_km=tuple(radii_km), row=row
    )
