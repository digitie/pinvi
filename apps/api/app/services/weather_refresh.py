"""일정 화면 "날씨 새로고침" — 날씨 위치 해석 캐시를 건너뛰고 다시 묻는다(2026-11-16 소유자 요청 15).

"이 날짜의 날씨 정보가 없습니다."는 대개 둘 중 하나다. (1) 그 날짜가 예보 범위 밖이다 — 새로고침으로 바뀌지
않는다. (2) `weather_location_links`에 저장된 위치 집합이 낡았다 — 해석할 때 적재 전이던 source(예보 격자 등)가
빠진 채로 `CACHE_TTL`(7일) 동안 재사용된다. 이 모듈은 (2)를 즉시 고친다.

- **Map 경로**(`pinvi_kor_travel_map_weather_enabled`, 운영 기본): 대상 feature마다 Map `/nearest` +
  `/locations?near=`로 위치 집합을 바로 다시 해석해 저장한다(`weather_map_resolver.nearest_location_set`).
  호출자는 응답을 받은 뒤 trip view를 다시 불러 새 집합으로 값을 읽는다. Map이 내는 값 자체(Valkey 상태)는 Map
  Dagster가 적재하므로 PinVi가 상류 수집을 일으키지는 않는다 — 상류를 당기는 API가 없다.
- **직접 경로**(플래그 off): 행을 `stale=True`로 표시한다. 다음 조회가 배경 해석(`weather_resolve_worker`)을 예약한다.

**속도 제한:** 같은 feature는 `REFRESH_COOLDOWN`(60초) 안에 다시 해석하지 않는다 — 판정은 그 행의 `resolved_at`
이라 worker·노드가 여럿이어도 공유되고, 방금 화면 조회가 해석한 행도 쉰다. 한 요청의 대상은 `MAX_REFRESH_FEATURES`
개까지(한 일자 분량)이고, Map 호출 동시성은 `REFRESH_CONCURRENCY`다. 사용자별 일반 한도(`authenticated_default`)는
미들웨어가 따로 건다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.db.session import release_read_connection
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_location_resolver import written_by_map
from app.services.weather_map_resolver import MapResolved, _persist, nearest_location_set

logger = logging.getLogger(__name__)

REFRESH_COOLDOWN: Final = timedelta(seconds=60)
MAX_REFRESH_FEATURES: Final = 30
REFRESH_CONCURRENCY: Final = 4


@dataclass(slots=True)
class WeatherRefreshResult:
    refreshed: list[str] = field(default_factory=list)
    cooldown: list[str] = field(default_factory=list)
    no_data: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    retry_after_seconds: int | None = None

    def note_cooldown(self, feature_id: str, remaining: timedelta) -> None:
        self.cooldown.append(feature_id)
        seconds = max(1, int(remaining.total_seconds() + 0.999))
        self.retry_after_seconds = max(self.retry_after_seconds or 0, seconds)


def _remaining_cooldown(row: WeatherLocationLink | None, *, now: datetime) -> timedelta | None:
    if row is None:
        return None
    remaining = REFRESH_COOLDOWN - (now - row.resolved_at)
    return remaining if remaining > timedelta(0) else None


async def refresh_weather_locations(
    db: AsyncSession,
    coords: Mapping[str, tuple[float, float]],
    *,
    map_client: KorTravelMapWeatherClient | None,
    now: datetime | None = None,
) -> WeatherRefreshResult:
    """`feature_id → (lat, lon)`의 위치 해석을 새로 한다. `map_client`가 없으면 직접 경로(stale 표시)다."""
    if len(coords) > MAX_REFRESH_FEATURES:
        raise ValueError(f"한 번에 {MAX_REFRESH_FEATURES}곳까지 새로고칠 수 있습니다.")
    current = now or datetime.now(UTC)
    result = WeatherRefreshResult()
    if not coords:
        return result
    rows = {
        row.feature_id: row
        for row in await db.scalars(
            select(WeatherLocationLink).where(WeatherLocationLink.feature_id.in_(list(coords)))
        )
    }
    # Map 호출(아래) 동안 풀 커넥션을 쥐지 않는다.
    await release_read_connection(db)

    due: list[str] = []
    for feature_id, (lat, lon) in coords.items():
        row = rows.get(feature_id)
        same_place = row is not None and row.lat == lat and row.lon == lon
        remaining = _remaining_cooldown(row, now=current) if same_place else None
        if remaining is not None:
            result.note_cooldown(feature_id, remaining)
        else:
            due.append(feature_id)

    if map_client is None:
        await _mark_stale(db, [fid for fid in due if fid in rows], now=current)
        result.refreshed.extend(due)
        return result

    semaphore = asyncio.Semaphore(REFRESH_CONCURRENCY)

    async def network(feature_id: str) -> MapResolved | KorTravelMapError | None:
        lat, lon = coords[feature_id]
        async with semaphore:
            try:
                return await nearest_location_set(map_client, lat=lat, lon=lon)
            except KorTravelMapError as exc:
                return exc

    resolved_list = await asyncio.gather(*(network(fid) for fid in due))
    for feature_id, resolved in zip(due, resolved_list, strict=True):
        if isinstance(resolved, KorTravelMapError):
            logger.warning(
                "weather_refresh.map_failed",
                extra={"feature_id": feature_id, "error_type": type(resolved).__name__},
            )
            result.failed.append(feature_id)
        elif resolved is None:
            result.no_data.append(feature_id)
        else:
            lat, lon = coords[feature_id]
            await _persist(
                db,
                rows.get(feature_id),
                feature_id=feature_id,
                lat=lat,
                lon=lon,
                resolved=resolved,
                now=current,
            )
            result.refreshed.append(feature_id)
    return result


async def _mark_stale(db: AsyncSession, feature_ids: list[str], *, now: datetime) -> None:
    """직접 경로 — 다음 조회가 배경 재해석을 예약하게 한다(Map 경로 행은 건드리지 않는다)."""
    if not feature_ids:
        return
    rows = list(
        await db.scalars(
            select(WeatherLocationLink).where(WeatherLocationLink.feature_id.in_(feature_ids))
        )
    )
    direct = [row.feature_id for row in rows if not written_by_map(row)]
    if direct:
        await db.execute(
            update(WeatherLocationLink)
            .where(WeatherLocationLink.feature_id.in_(direct))
            .values(stale=True, resolved_at=now)
        )
    await db.commit()
