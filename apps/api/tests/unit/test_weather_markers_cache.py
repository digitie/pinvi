"""weather `/markers` 결과의 짧은 TTL 캐시(#621, `app/services/weather_markers_cache.py`).

핵심 단언:

- 키는 정규화한 location 집합이다(순서·중복 무관). TTL 안에서는 다시 부르지 않는다.
- 같은 키의 동시 요청은 upstream 호출 하나로 합친다(single-flight).
- 성공만 캐시한다. 실패는 캐시하지 않고 기다리던 모두에게 그대로 전한다.
- 기다리던 요청이 취소돼도(view 예산 초과) 공유 조회는 끝까지 가서 캐시를 채운다. 그 조회는 호출자의 짧은
  weather deadline 범위를 물려받지 않는다.
- 항목 수·location 수 상한으로 메모리를 묶는다(LRU).
- 캐시되는 값은 공개 weather 필드뿐이다(사용자별 필드 없음).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Sequence

import pytest

from app.clients import kor_travel_weather as kw
from app.clients.kor_travel_weather import (
    KorTravelWeatherUnavailable,
    MeasurementPointOut,
    WeatherMarkerOut,
    WeatherValueOut,
    kor_travel_weather_call_deadline,
)
from app.services import weather_markers_cache as wmc


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Weather:
    def __init__(self, *, fail_times: int = 0, gate: asyncio.Event | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_times = fail_times
        self.gate = gate
        self.scope_deadlines: list[float | None] = []

    async def markers(self, location_ids: Sequence[str]) -> tuple[WeatherMarkerOut, ...]:
        self.calls.append(list(location_ids))
        scope = kw._call_scope.get()
        self.scope_deadlines.append(None if scope is None else scope.deadline)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_times > 0:
            self.fail_times -= 1
            raise KorTravelWeatherUnavailable("down")
        return tuple(WeatherMarkerOut(location_id=loc) for loc in location_ids)


def _cache(clock: _Clock, **kwargs: float) -> wmc.WeatherMarkersCache:
    params: dict[str, float] = {
        "ttl_seconds": 90.0,
        "max_entries": 8,
        "max_locations": 100,
        "fetch_budget_seconds": 8.0,
    }
    params.update(kwargs)
    return wmc.WeatherMarkersCache(
        ttl_seconds=params["ttl_seconds"],
        max_entries=int(params["max_entries"]),
        max_locations=int(params["max_locations"]),
        fetch_budget_seconds=params["fetch_budget_seconds"],
        clock=clock,
    )


def _count(outcome: str) -> float:
    value = wmc.MARKERS_CACHE_REQUESTS.labels(outcome=outcome)._value.get()
    return float(value)


async def test_normalized_location_set_hits_within_ttl_and_expires_after() -> None:
    clock = _Clock()
    cache = _cache(clock)
    weather = _Weather()
    hits, misses = _count("hit"), _count("miss")

    first = await cache.get(weather, ["b", "a", "a"])  # type: ignore[arg-type]
    second = await cache.get(weather, ["a", "b"])  # type: ignore[arg-type]
    assert {m.location_id for m in first} == {"a", "b"}
    assert second == first
    assert weather.calls == [["a", "b"]]  # 정규화(정렬·중복 제거)한 집합으로 한 번만
    assert _count("miss") - misses == 1
    assert _count("hit") - hits == 1

    clock.now += 91.0
    await cache.get(weather, ["a", "b"])  # type: ignore[arg-type]
    assert len(weather.calls) == 2


async def test_concurrent_identical_requests_share_one_upstream_call() -> None:
    cache = _cache(_Clock())
    gate = asyncio.Event()
    weather = _Weather(gate=gate)
    coalesced = _count("coalesced")

    tasks = [asyncio.create_task(cache.get(weather, ["x", "y"])) for _ in range(5)]  # type: ignore[arg-type]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*tasks)
    assert weather.calls == [["x", "y"]]
    assert all(r == results[0] for r in results)
    assert _count("coalesced") - coalesced == 4


async def test_failures_are_not_cached_and_reach_every_waiter() -> None:
    cache = _cache(_Clock())
    gate = asyncio.Event()
    weather = _Weather(fail_times=1, gate=gate)
    errors = _count("error")

    tasks = [asyncio.create_task(cache.get(weather, ["x"])) for _ in range(2)]  # type: ignore[arg-type]
    await asyncio.sleep(0)
    gate.set()
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(o, KorTravelWeatherUnavailable) for o in outcomes)
    assert _count("error") - errors == 1

    # 다음 요청은 다시 upstream에 간다(실패는 캐시하지 않는다).
    assert [m.location_id for m in await cache.get(weather, ["x"])] == ["x"]  # type: ignore[arg-type]
    assert len(weather.calls) == 2


async def test_cancelled_waiter_does_not_cancel_the_shared_fetch_and_it_fills_the_cache() -> None:
    cache = _cache(_Clock())
    gate = asyncio.Event()
    weather = _Weather(gate=gate)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await cache.get(weather, ["slow"])  # type: ignore[arg-type]
    gate.set()
    await cache.wait_idle()

    assert [m.location_id for m in await cache.get(weather, ["slow"])] == ["slow"]  # type: ignore[arg-type]
    assert weather.calls == [["slow"]]


async def test_shared_fetch_runs_in_its_own_deadline_not_the_callers() -> None:
    cache = _cache(_Clock(), fetch_budget_seconds=8.0)
    weather = _Weather()
    loop = asyncio.get_running_loop()
    caller_deadline = loop.time() + 0.5
    with kor_travel_weather_call_deadline(caller_deadline):
        await cache.get(weather, ["d"])  # type: ignore[arg-type]
    (fetch_deadline,) = weather.scope_deadlines
    assert fetch_deadline is not None
    assert fetch_deadline > caller_deadline + 5.0


async def test_memory_is_bounded_by_entries_and_locations() -> None:
    cache = _cache(_Clock(), max_entries=2, max_locations=100)
    weather = _Weather()
    for key in (["k1"], ["k2"], ["k3"]):
        await cache.get(weather, key)  # type: ignore[arg-type]
    await cache.get(weather, ["k1"])  # type: ignore[arg-type]  # 가장 오래된 k1은 밀려났다
    assert weather.calls == [["k1"], ["k2"], ["k3"], ["k1"]]
    assert cache.size() <= 2

    small = _cache(_Clock(), max_entries=10, max_locations=3)
    weather2 = _Weather()
    await small.get(weather2, ["a", "b"])  # type: ignore[arg-type]
    await small.get(weather2, ["c", "d"])  # type: ignore[arg-type]  # 합 4 > 3 → a,b 밀림
    await small.get(weather2, ["a", "b"])  # type: ignore[arg-type]
    assert len(weather2.calls) == 3
    assert small.location_count() <= 3

    # 상한보다 큰 단일 집합은 캐시하지 않는다(그래도 결과는 돌려준다).
    huge = await small.get(weather2, ["p", "q", "r", "s"])  # type: ignore[arg-type]
    assert len(huge) == 4
    assert small.location_count() <= 3


async def test_ttl_zero_disables_caching() -> None:
    cache = _cache(_Clock(), ttl_seconds=0.0)
    weather = _Weather()
    await cache.get(weather, ["z"])  # type: ignore[arg-type]
    await cache.get(weather, ["z"])  # type: ignore[arg-type]
    assert len(weather.calls) == 2


def test_cached_values_carry_only_public_weather_fields() -> None:
    """캐시는 사용자 사이에 공유된다 — 담기는 타입에 사용자·여행 식별 필드가 없어야 한다."""
    forbidden = ("user", "owner", "trip", "email", "session", "token", "poi", "request", "users")
    for cls in (WeatherMarkerOut, WeatherValueOut, MeasurementPointOut):
        names = [f.name for f in dataclasses.fields(cls)]
        # 이름 조각 단위로 본다(`measurement_point`의 "point"가 "poi"로 걸리지 않게).
        leaked = [n for n in names if any(word in n.split("_") for word in forbidden)]
        assert leaked == [], (cls.__name__, leaked)
        assert cls.__dataclass_params__.frozen, cls.__name__  # type: ignore[attr-defined]
    assert {f.name for f in dataclasses.fields(WeatherMarkerOut)} == {
        "location_id",
        "measurement_point",
        "latest",
        "alerts",
    }


async def test_module_level_cache_follows_settings_and_resets() -> None:
    from app.core.config import settings

    assert 60.0 <= settings.pinvi_kor_travel_weather_markers_cache_ttl_seconds <= 120.0
    weather = _Weather()
    await wmc.cached_markers(weather, ["m"])  # type: ignore[arg-type]
    await wmc.cached_markers(weather, ["m"])  # type: ignore[arg-type]
    assert len(weather.calls) == 1
    wmc.reset_weather_markers_cache()
    await wmc.cached_markers(weather, ["m"])  # type: ignore[arg-type]
    assert len(weather.calls) == 2


async def test_fresh_bypasses_the_cache_for_admin_diagnostics() -> None:
    weather = _Weather()
    await wmc.cached_markers(weather, ["f"])  # type: ignore[arg-type]
    await wmc.cached_markers(weather, ["f"], fresh=True)  # type: ignore[arg-type]
    assert len(weather.calls) == 2


async def test_different_clients_do_not_share_entries_or_fetches() -> None:
    cache = _cache(_Clock())
    first, second = _Weather(), _Weather()
    await cache.get(first, ["c"])  # type: ignore[arg-type]
    await cache.get(second, ["c"])  # type: ignore[arg-type]
    assert first.calls == [["c"]] and second.calls == [["c"]]


async def test_shared_fetch_does_not_inherit_the_callers_context() -> None:
    import contextvars

    marker: contextvars.ContextVar[str | None] = contextvars.ContextVar("marker", default=None)
    seen: list[str | None] = []

    class _Probe(_Weather):
        async def markers(self, location_ids: Sequence[str]) -> tuple[WeatherMarkerOut, ...]:
            seen.append(marker.get())
            return await super().markers(location_ids)

    marker.set("request-1")
    await _cache(_Clock()).get(_Probe(), ["ctx"])  # type: ignore[arg-type]
    assert seen == [None]
