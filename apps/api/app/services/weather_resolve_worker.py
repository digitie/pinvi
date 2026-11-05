"""직접 weather 캐시 워밍(#621). 재요청 가능한 손실 허용 작업이며 업무 outbox가 아니다.

worker/client별 두 실행 자리와 제한된 대기/음성 캐시만 소유한다. 요청 세션이나
request deadline/인증 context를 보관하지 않는다. worker 종료 시 미완료 작업은 취소하고
다음 요청이 다시 예약한다. 기존 Map/좌표/캐시 삭제 뒤 늦게 도착한 결과는 저장하지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from contextvars import Context
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.dml import Insert, Update

from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.core.config import settings
from app.db import session as db_session
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_location_resolver import (
    WeatherLocationNoData,
    WeatherLocationPending,
    _dedupe_preserving_order,
    _measurement_point_dict,
    _resolve_via_client,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Version:
    updated_at: datetime
    resolved_at: datetime
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class _Job:
    feature_id: str
    lat: float
    lon: float
    radii_km: tuple[float, ...]
    version: _Version | None

    @property
    def key(self) -> tuple[str, float, float, tuple[float, ...]]:
        return self.feature_id, self.lat, self.lon, self.radii_km


class WeatherResolveWorker:
    def __init__(
        self,
        client: KorTravelWeatherClient,
        *,
        session_factory: Any | None = None,
        capacity: int = 128,
        concurrency: int = 2,
        negative_ttl: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if capacity < 1 or concurrency < 1 or negative_ttl <= 0:
            raise ValueError("cache warming limits must be positive")
        self._client = client
        self._factory = session_factory or db_session.async_session_factory
        self._capacity = capacity
        self._concurrency = concurrency
        self._negative_ttl = negative_ttl
        self._clock = clock or asyncio.get_running_loop().time
        self._queue: asyncio.Queue[str] = asyncio.Queue(capacity)
        self._latest: dict[str, _Job] = {}
        self._negative: OrderedDict[
            tuple[str, float, float, tuple[float, ...]],
            tuple[float, WeatherLocationNoData | WeatherLocationPending],
        ] = OrderedDict()
        self._tasks: list[asyncio.Task[None]] = []
        self._closed = False

    def schedule(
        self,
        *,
        feature_id: str,
        lat: float,
        lon: float,
        radii_km: tuple[float, ...],
        row: WeatherLocationLink | None,
    ) -> WeatherLocationNoData | WeatherLocationPending:
        if self._closed or settings.pinvi_kor_travel_map_weather_enabled:
            return WeatherLocationPending()
        job = _Job(
            feature_id,
            lat,
            lon,
            radii_km,
            None if row is None else _Version(row.updated_at, row.resolved_at, row.lat, row.lon),
        )
        now = self._clock()
        for key in [key for key, (until, _) in self._negative.items() if until <= now]:
            self._negative.pop(key)
        negative = self._negative.get(job.key)
        if negative is not None:
            return negative[1]
        previous = self._latest.get(feature_id)
        if previous is not None:
            if previous != job:
                # 실행 중 좌표가 바뀌면 이전 결과를 버리고 최신 예약만 이어서 실행한다.
                self._latest[feature_id] = job
            return WeatherLocationPending()
        if self._queue.full() or len(self._latest) >= self._capacity + self._concurrency:
            return WeatherLocationPending()
        self._latest[feature_id] = job
        self._queue.put_nowait(feature_id)
        if not self._tasks:
            self._tasks = [
                asyncio.create_task(self._run(), name="pinvi-weather-resolve", context=Context())
                for _ in range(self._concurrency)
            ]
        return WeatherLocationPending()

    def _remember(self, job: _Job, result: WeatherLocationNoData | WeatherLocationPending) -> None:
        self._negative[job.key] = self._clock() + self._negative_ttl, result
        self._negative.move_to_end(job.key)
        while len(self._negative) > self._capacity:
            self._negative.popitem(last=False)

    async def _run(self) -> None:
        while True:
            feature_id = await self._queue.get()
            job = self._latest[feature_id]
            committed: _Version | None = None
            try:
                if not settings.pinvi_kor_travel_map_weather_enabled:
                    committed = await self._resolve(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._latest.get(feature_id) is job:
                    self._remember(job, WeatherLocationPending())
                logger.warning(
                    "weather_resolve.background_failed", extra={"error_type": type(exc).__name__}
                )
            finally:
                latest = self._latest.get(feature_id)
                if not self._closed and latest is not None and latest is not job:
                    if committed is not None and latest.version == job.version:
                        # commit을 기다리는 동안 새 좌표가 예약됐어도, 방금 쓴 내 결과만 이어서
                        # 교체할 수 있게 한다. 다른 Map/좌표 변경의 version은 따라가지 않는다.
                        self._latest[feature_id] = replace(latest, version=committed)
                    try:
                        self._queue.put_nowait(feature_id)
                    except asyncio.QueueFull:
                        self._latest.pop(feature_id, None)
                else:
                    self._latest.pop(feature_id, None)
                self._queue.task_done()

    async def _resolve(self, job: _Job) -> _Version | None:
        # read_timeout은 client resolve에만 주며, 반경 세 개 전체도 140초 안에 종료한다.
        async with asyncio.timeout(140):
            resolved = await _resolve_via_client(
                self._client, lat=job.lat, lon=job.lon, radii_km=job.radii_km
            )
        if self._latest.get(job.feature_id) is not job:
            return None
        if resolved is None:
            self._remember(job, WeatherLocationNoData())
            return None
        if settings.pinvi_kor_travel_map_weather_enabled:
            return None
        values = {
            "location_id": resolved.location.location_id,
            "source_location_ids": list(
                _dedupe_preserving_order(
                    [
                        resolved.location.location_id,
                        *(loc.location_id for loc in resolved.source_locations),
                    ]
                )
            ),
            "lat": job.lat,
            "lon": job.lon,
            "distance_km": resolved.distance_km,
            "measurement_point": _measurement_point_dict(resolved),
            "resolved_at": datetime.now(UTC),
            "stale": False,
        }
        async with self._factory() as db:
            statement: Insert | Update
            if job.version is None:
                # 다른 요청이 먼저 만든 행을, 행이 없을 때 출발한 오래된 결과로 덮어쓰지 않는다.
                statement = (
                    pg_insert(WeatherLocationLink)
                    .values(feature_id=job.feature_id, **values)
                    .on_conflict_do_nothing(index_elements=[WeatherLocationLink.feature_id])
                )
            else:
                version = job.version
                # 이미 있던 행이 삭제됐으면 재생성하지 않는다. Map/좌표 변경도 같은 fence로 막는다.
                statement = (
                    update(WeatherLocationLink)
                    .where(
                        WeatherLocationLink.feature_id == job.feature_id,
                        WeatherLocationLink.updated_at == version.updated_at,
                        WeatherLocationLink.resolved_at == version.resolved_at,
                        WeatherLocationLink.lat == version.lat,
                        WeatherLocationLink.lon == version.lon,
                    )
                    .values(**values, updated_at=func.now())
                )
            if self._latest.get(job.feature_id) is not job:
                return None
            result = (
                await db.execute(
                    statement.returning(
                        WeatherLocationLink.updated_at,
                        WeatherLocationLink.resolved_at,
                    )
                )
            ).first()
            if (
                self._latest.get(job.feature_id) is not job
                or settings.pinvi_kor_travel_map_weather_enabled
            ):
                await db.rollback()
                return None
            await db.commit()
            return (
                _Version(result.updated_at, result.resolved_at, job.lat, job.lon)
                if result is not None
                else None
            )

    async def drain(self) -> None:
        """테스트/명시적 관측에서 현재 예약이 끝나길 기다린다. 요청 경로는 호출하지 않는다."""
        await self._queue.join()

    async def close(self) -> None:
        self._closed = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._latest.clear()
        self._negative.clear()
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()


_WORKERS: WeakKeyDictionary[KorTravelWeatherClient, WeatherResolveWorker] = WeakKeyDictionary()


def get_weather_resolve_worker(client: KorTravelWeatherClient) -> WeatherResolveWorker:
    worker = _WORKERS.get(client)
    if worker is None:
        worker = WeatherResolveWorker(client)
        _WORKERS[client] = worker
    return worker


async def close_weather_resolve_worker(client: KorTravelWeatherClient) -> None:
    worker = _WORKERS.pop(client, None)
    if worker is not None:
        await worker.close()
