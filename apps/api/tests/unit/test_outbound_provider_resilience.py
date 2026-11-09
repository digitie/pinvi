"""소유 MockTransport로 provider 포화·timeout 회복·취소·늦은 결과를 검증한다."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_geo import KorTravelGeoClient, KorTravelGeoUnavailable
from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapUnavailable
from app.clients.kor_travel_weather import KorTravelWeatherClient, KorTravelWeatherUnavailable


@asynccontextmanager
async def _provider(
    name: str, handler: Any, **kwargs: Any
) -> AsyncIterator[tuple[Any, Any, type[Exception]]]:
    http = httpx.AsyncClient(base_url="http://fixture.test", transport=httpx.MockTransport(handler))
    if name == "map":
        client = KorTravelMapClient(http, max_attempts=1, **kwargs)
        error = KorTravelMapUnavailable

        async def call() -> Any:
            return await client.get_feature("fixture")
    elif name == "geo":
        client = KorTravelGeoClient(http, api_key="fixture-key", max_attempts=1, **kwargs)
        error = KorTravelGeoUnavailable

        async def call() -> Any:
            return await client.geocode(query="fixture")
    else:
        client = KorTravelWeatherClient(http, max_attempts=1, **kwargs)
        error = KorTravelWeatherUnavailable

        async def call() -> Any:
            return await client.latest("fixture")

    try:
        yield client, call, error
    finally:
        await client.aclose()


def _success(name: str) -> httpx.Response:
    if name == "geo":
        return httpx.Response(200, json={"status": "ok", "candidates": []})
    return httpx.Response(200, json={"data": [] if name == "weather" else {}, "meta": {}})


@pytest.mark.parametrize("name", ["map", "geo", "weather"])
async def test_full_provider_rejects_immediately_and_cancellation_returns_capacity(
    name: str,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 16:
            started.set()
        await release.wait()
        return _success(name)

    async with _provider(name, handler) as (_client, call, error):
        pending = [asyncio.create_task(call()) for _ in range(16)]
        try:
            await asyncio.wait_for(started.wait(), 1)
            with pytest.raises(error, match="동시 호출 상한"):
                await asyncio.wait_for(call(), 0.1)
            assert attempts == 16
            if name == "geo":
                with pytest.raises(error, match="동시 호출 상한"):
                    await asyncio.wait_for(_client.healthz(), 0.1)
                assert attempts == 16
            pending[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending[0]
            release.set()
            await asyncio.gather(*pending[1:])
            await call()
            assert attempts == 17
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.parametrize("name", ["map", "geo"])
async def test_transport_timeouts_open_provider_circuit_before_fourth_call(name: str) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("fixture timeout", request=request)

    async with _provider(name, handler) as (_client, call, error):
        for _ in range(3):
            with pytest.raises(error):
                await call()
        with pytest.raises(error, match="회로 열림"):
            await call()
        assert attempts == 3


async def test_weather_timeout_circuit_stays_open_across_views_more_than_thirty_seconds_apart() -> (
    None
):
    now = [0.0]
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("fixture timeout", request=request)

    async with _provider("weather", handler, clock=lambda: now[0]) as (_client, call, error):
        for _ in range(3):
            with pytest.raises(error):
                await call()
        now[0] = 31.0
        with pytest.raises(error, match="회로 열림"):
            await call()
        assert attempts == 3


async def test_old_weather_success_does_not_close_a_newly_opened_circuit() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await release.wait()
            return _success("weather")
        raise httpx.ReadTimeout("fixture timeout", request=request)

    async with _provider("weather", handler) as (_client, call, error):
        old = asyncio.create_task(call())
        try:
            await asyncio.wait_for(started.wait(), 1)
            for _ in range(3):
                with pytest.raises(error):
                    await call()
            release.set()
            await old
            with pytest.raises(error, match="회로 열림"):
                await call()
            assert attempts == 4
        finally:
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)


@pytest.mark.parametrize("name", ["map", "geo"])
async def test_provider_single_half_open_trial_and_cancelled_trial_returns_slot(name: str) -> None:
    now = [0.0]
    trial_started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        trial_started.set()
        await release.wait()
        return _success(name)

    async with _provider(name, handler, clock=lambda: now[0], max_concurrent_requests=2) as (
        _client,
        call,
        error,
    ):
        for _ in range(3):
            with pytest.raises(error):
                await call()
        now[0] = 31.0
        with pytest.raises(error, match="회로 열림"):
            await call()
        assert attempts == 3
        now[0] = 120.0
        trial = asyncio.create_task(call())
        try:
            await asyncio.wait_for(trial_started.wait(), 1)
            with pytest.raises(error, match="회로 열림"):
                await asyncio.wait_for(call(), 0.1)
            assert attempts == 4
            trial.cancel()
            with pytest.raises(asyncio.CancelledError):
                await trial
            release.set()
            await asyncio.wait_for(call(), 1)
            await call()
            assert attempts == 6
        finally:
            trial.cancel()
            await asyncio.gather(trial, return_exceptions=True)


@pytest.mark.parametrize("name", ["map", "geo"])
@pytest.mark.parametrize("old_fails", [False, True])
async def test_provider_ignores_late_result_from_before_circuit_open(
    name: str, old_fails: bool
) -> None:
    now = [0.0]
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        index = attempts
        if index == 1:
            started.set()
            await release.wait()
            if not old_fails:
                return _success(name)
        if index <= 4:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return _success(name)

    async with _provider(name, handler, clock=lambda: now[0]) as (_client, call, error):
        old = asyncio.create_task(call())
        try:
            await asyncio.wait_for(started.wait(), 1)
            for _ in range(3):
                with pytest.raises(error):
                    await call()
            now[0] = 119.0
            release.set()
            if old_fails:
                with pytest.raises(error):
                    await old
            else:
                await old
            with pytest.raises(error, match="회로 열림"):
                await call()
            assert attempts == 4
            now[0] = 120.0
            await call()
            assert attempts == 5
        finally:
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)


@pytest.mark.parametrize("name", ["map", "geo", "weather"])
async def test_local_pool_timeout_never_opens_remote_circuit_or_leaks_capacity(name: str) -> None:
    fail = True
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if fail:
            raise httpx.PoolTimeout("fixture pool busy", request=request)
        return _success(name)

    async with _provider(name, handler, max_concurrent_requests=1) as (_client, call, error):
        for _ in range(5):
            with pytest.raises(error, match="풀 대기"):
                await call()
        fail = False
        await call()
        assert attempts == 6


async def test_map_weather_bulkhead_rejections_do_not_open_its_remote_circuit() -> None:
    from app.clients.kor_travel_map_weather import (
        KorTravelMapWeatherClient,
        KorTravelMapWeatherUnavailable,
    )

    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        started.set()
        await release.wait()
        return _success("map")

    http = httpx.AsyncClient(base_url="http://fixture.test", transport=httpx.MockTransport(handler))
    client = KorTravelMapClient(
        http, service_token="fixture", max_attempts=1, max_concurrent_requests=1
    )
    weather = KorTravelMapWeatherClient(client)
    # weather는 자기 bulkhead만 쓴다(#621) — 자리를 채우는 것도 weather 호출이어야 한다.
    held = asyncio.create_task(weather.nearest(lon=126.9, lat=37.5))
    try:
        await asyncio.wait_for(started.wait(), 1)
        for _ in range(3):
            with pytest.raises(KorTravelMapWeatherUnavailable) as info:
                await asyncio.wait_for(weather.nearest(lon=126.9, lat=37.5), 0.1)
            assert info.value.code == "BULKHEAD_FULL"
        assert attempts == 1
        release.set()
        await held
        assert await weather.nearest(lon=126.9, lat=37.5) == {}
        assert attempts == 2
    finally:
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)
        await client.aclose()
