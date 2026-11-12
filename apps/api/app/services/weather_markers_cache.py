"""kor-travel-weather `/markers` 결과의 짧은 TTL 캐시(#621).

trip view는 view마다 같은 위치들의 `/markers`(현재값+특보)를 다시 불렀다(운영 p50 2.2 s·p95 3.7 s). 값은 관측·
특보 갱신 주기보다 훨씬 자주 조회되므로 짧게 캐시한다.

- **키**: 정규화한 location 집합(정렬·중복 제거). PinVi는 `kind`를 보내지 않는다 — 보내게 되면 키에 넣는다.
- **공유 안전**: 값은 공개 weather(`WeatherMarkerOut` — location·측정소·값·특보)뿐이다. 요청자·여행 정보는 키에도
  값에도 없다(`tests/unit/test_weather_markers_cache.py`가 필드를 고정한다). 값은 frozen dataclass라 호출자가
  바꿀 수 없다.
- **성공만** 담는다. 실패는 담지 않고 기다리던 요청 모두에 그대로 전한다(회로·bulkhead 거부 포함).
- **single-flight**: 같은 키의 동시 요청은 upstream 호출 하나를 기다린다. 공유 조회는 별도 task라 기다리던 요청이
  예산을 넘겨 취소돼도 끝까지 가서 캐시를 채운다. 그 조회는 호출자의 짧은 weather deadline 범위를 물려받지 않고
  자기 예산(`..._markers_fetch_budget_seconds`)을 쓴다.
- **메모리 상한**: 항목 수와 담긴 location 수 합(LRU). 상한보다 큰 집합 하나는 담지 않는다.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from prometheus_client import Counter, Gauge

from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    WeatherMarkerOut,
    kor_travel_weather_detached_call_deadline,
)
from app.core.config import settings

#: hit=캐시 적중, miss=upstream 조회 시작, coalesced=진행 중 조회에 합류, error=공유 조회 실패(캐시 안 함),
#: bypass=관리자 진단처럼 캐시를 거치지 않은 호출.
MARKERS_CACHE_REQUESTS = Counter(
    "pinvi_api_weather_markers_cache_requests_total",
    "kor-travel-weather /markers cache lookups by outcome.",
    ("outcome",),
)
MARKERS_CACHE_ENTRIES = Gauge(
    "pinvi_api_weather_markers_cache_entries",
    "Entries currently held in the kor-travel-weather /markers cache.",
)

# (client 식별, 정렬한 location id들). 운영은 lifespan당 client 하나다 — client를 키에 넣는 것은 닫힌 client의
# 진행 중 조회에 새 client 요청이 합류하지 않게 하려는 것이다.
_Key = tuple[int, tuple[str, ...]]
_Markers = tuple[WeatherMarkerOut, ...]


@dataclass(slots=True)
class _Entry:
    expires_at: float
    value: _Markers


class WeatherMarkersCache:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        max_locations: int,
        fetch_budget_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._max_locations = max_locations
        self._fetch_budget = fetch_budget_seconds
        self._clock = clock
        self._entries: OrderedDict[_Key, _Entry] = OrderedDict()
        self._locations = 0
        self._inflight: dict[_Key, asyncio.Task[_Markers]] = {}

    def size(self) -> int:
        return len(self._entries)

    def location_count(self) -> int:
        return self._locations

    async def get(self, client: KorTravelWeatherClient, location_ids: Sequence[str]) -> _Markers:
        ids = tuple(sorted(set(location_ids)))
        if not ids:
            raise ValueError("location_ids는 최소 1개 이상이어야 합니다.")
        key: _Key = (id(client), ids)
        entry = self._entries.get(key)
        if entry is not None:
            if entry.expires_at > self._clock():
                self._entries.move_to_end(key)
                MARKERS_CACHE_REQUESTS.labels(outcome="hit").inc()
                return entry.value
            self._drop(key)
        task = self._inflight.get(key)
        if task is None:
            MARKERS_CACHE_REQUESTS.labels(outcome="miss").inc()
            # 공유 조회는 처음 요청한 쪽의 문맥(request_id·deadline 범위)을 물려받지 않는다.
            task = asyncio.get_running_loop().create_task(
                self._fetch(client, ids), context=contextvars.Context()
            )
            self._inflight[key] = task
            task.add_done_callback(lambda done: self._finish(key, done))
        else:
            MARKERS_CACHE_REQUESTS.labels(outcome="coalesced").inc()
        # 기다리던 요청이 취소돼도(view 예산) 공유 조회는 계속된다.
        return await asyncio.shield(task)

    async def _fetch(self, client: KorTravelWeatherClient, ids: tuple[str, ...]) -> _Markers:
        deadline = asyncio.get_running_loop().time() + self._fetch_budget
        with kor_travel_weather_detached_call_deadline(deadline):
            return await client.markers(list(ids))

    def _finish(self, key: _Key, task: asyncio.Task[_Markers]) -> None:
        if self._inflight.get(key) is task:
            del self._inflight[key]
        if task.cancelled():
            return
        exc = (
            task.exception()
        )  # 기다리던 요청이 모두 떠났어도 '회수 안 된 예외' 경고를 남기지 않는다.
        if exc is not None:
            MARKERS_CACHE_REQUESTS.labels(outcome="error").inc()
            return
        self._store(key, task.result())

    def _store(self, key: _Key, value: _Markers) -> None:
        if self._ttl <= 0 or len(key[1]) > self._max_locations:
            return
        self._drop(key)
        self._entries[key] = _Entry(expires_at=self._clock() + self._ttl, value=value)
        self._locations += len(key[1])
        while self._entries and (
            len(self._entries) > self._max_entries or self._locations > self._max_locations
        ):
            oldest = next(iter(self._entries))
            self._drop(oldest)
        MARKERS_CACHE_ENTRIES.set(len(self._entries))

    def _drop(self, key: _Key) -> None:
        if self._entries.pop(key, None) is not None:
            self._locations -= len(key[1])
            MARKERS_CACHE_ENTRIES.set(len(self._entries))

    async def wait_idle(self) -> None:
        """진행 중인 공유 조회가 모두 끝날 때까지 기다린다(테스트·종료용)."""
        while self._inflight:
            await asyncio.gather(*self._inflight.values(), return_exceptions=True)
            await asyncio.sleep(0)  # 완료 콜백(_finish)이 돌 차례를 준다

    def clear(self) -> None:
        for task in self._inflight.values():
            # 테스트 사이에는 이전 event loop가 이미 닫혀 있을 수 있다.
            with contextlib.suppress(RuntimeError):
                task.cancel()
        self._inflight.clear()
        self._entries.clear()
        self._locations = 0
        MARKERS_CACHE_ENTRIES.set(0)


_cache: WeatherMarkersCache | None = None


def weather_markers_cache() -> WeatherMarkersCache:
    global _cache
    if _cache is None:
        _cache = WeatherMarkersCache(
            ttl_seconds=settings.pinvi_kor_travel_weather_markers_cache_ttl_seconds,
            max_entries=settings.pinvi_kor_travel_weather_markers_cache_max_entries,
            max_locations=settings.pinvi_kor_travel_weather_markers_cache_max_locations,
            fetch_budget_seconds=settings.pinvi_kor_travel_weather_markers_fetch_budget_seconds,
        )
    return _cache


def reset_weather_markers_cache() -> None:
    """프로세스 캐시를 비우고 설정을 다시 읽게 한다(테스트용)."""
    global _cache
    if _cache is not None:
        _cache.clear()
    _cache = None


async def cached_markers(
    client: KorTravelWeatherClient, location_ids: Sequence[str], *, fresh: bool = False
) -> _Markers:
    """캐시를 거친 `/markers`. `fresh=True`(관리자 진단)는 캐시를 읽지도 채우지도 않고 바로 부른다."""
    if fresh:
        MARKERS_CACHE_REQUESTS.labels(outcome="bypass").inc()
        return await client.markers(location_ids)
    return await weather_markers_cache().get(client, location_ids)
