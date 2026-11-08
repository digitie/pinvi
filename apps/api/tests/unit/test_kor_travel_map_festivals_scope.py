"""#714 — 공개 월별 축제의 첫 조회 월 ReadTimeout이 ``features`` 회로를 열던 문제.

운영 2026-11-08: ``/v1/public/festivals/monthly`` 첫 조회 월(1·2월)이 PinVi read timeout(5초)을 넘어 503,
그 timeout들이 ``scope=features`` 회로를 열어 검색·상세까지 몇 분 거부됐다. 같은 월을 직후 Map에 직접
부르면 0.02~0.33초(캐시가 찬 뒤).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.clients.kor_travel_map import (
    FESTIVALS_MAX_CONCURRENT_REQUESTS,
    FESTIVALS_MONTHLY_READ_TIMEOUT_SECONDS,
    KorTravelMapClient,
    KorTravelMapUnavailable,
)

Handler = Callable[[httpx.Request], httpx.Response]
_MONTHLY = {
    "data": {"months": [], "items": []},
    "meta": {"page": {"next_cursor": None, "total": 0}},
}


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _client(handler: Handler, clock: _Clock | None = None) -> KorTravelMapClient:
    http = httpx.AsyncClient(
        base_url="http://map.test", transport=httpx.MockTransport(handler), timeout=5.0
    )
    return KorTravelMapClient(
        http,
        max_attempts=3,
        backoff_base_seconds=0.0,
        service_token="svc-token-secret",
        clock=clock or _Clock(),
    )


async def test_festival_timeouts_do_not_cut_search_detail_or_viewport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/public/festivals/monthly":
            raise httpx.ReadTimeout("cold month", request=request)
        if request.url.path == "/v1/features/search":
            return httpx.Response(200, json={"data": {"items": []}, "meta": {}})
        if request.url.path == "/v1/features/in-bounds":
            return httpx.Response(200, json={"data": {"items": [], "clusters": []}, "meta": {}})
        return httpx.Response(200, json={"data": {"feature_id": "f_x"}, "meta": {}})

    client = _client(handler)
    for month in (1, 2, 3):
        with pytest.raises(KorTravelMapUnavailable):
            await client.public_festivals_monthly(year=2026, month=month)
    with pytest.raises(KorTravelMapUnavailable) as info:
        await client.public_festivals_monthly(year=2026, month=4)
    assert info.value.code == "CIRCUIT_OPEN"
    # 축제 회로만 열렸다 — 검색·상세·viewport는 그대로 Map에 닿는다.
    assert (await client.search_features(q="안동하회마을"))["items"] == []
    assert await client.get_feature("f_x") == {"feature_id": "f_x"}
    await client.features_in_bounds(
        min_lon=128.0, min_lat=36.0, max_lon=129.0, max_lat=37.0, zoom=9
    )
    await client.aclose()


async def test_monthly_gets_a_longer_read_budget_only_for_itself() -> None:
    seen: dict[str, dict[str, float | None]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = dict(request.extensions["timeout"])
        if request.url.path == "/v1/public/festivals/monthly":
            return httpx.Response(200, json=_MONTHLY)
        return httpx.Response(200, json={"data": {"feature_id": "f_x"}, "meta": {}})

    client = _client(handler)
    await client.public_festivals_monthly(year=2026, month=1)
    await client.get_feature("f_x")
    monthly = seen["/v1/public/festivals/monthly"]
    assert monthly["read"] == FESTIVALS_MONTHLY_READ_TIMEOUT_SECONDS
    assert FESTIVALS_MONTHLY_READ_TIMEOUT_SECONDS > 5.0
    # 연결은 짧은 기본값을 그대로 쓰고, 다른 표면의 read는 바뀌지 않는다.
    assert monthly["connect"] == 5.0
    assert seen["/v1/features/f_x"]["read"] == 5.0
    await client.aclose()


async def test_successful_months_are_cached_briefly_and_failures_are_not() -> None:
    sent: list[str] = []
    fail_next = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url.params))
        if fail_next["value"]:
            fail_next["value"] = False
            raise httpx.ReadTimeout("cold month", request=request)
        return httpx.Response(200, json=_MONTHLY)

    clock = _Clock()
    client = _client(handler, clock)
    first = await client.public_festivals_monthly(year=2026, month=1, page_size=12)
    again = await client.public_festivals_monthly(year=2026, month=1, page_size=12)
    assert again == first
    assert len(sent) == 1
    # 다른 질의는 따로 부른다.
    await client.public_festivals_monthly(year=2026, month=2, page_size=12)
    assert len(sent) == 2
    # 실패는 캐시하지 않는다.
    fail_next["value"] = True
    with pytest.raises(KorTravelMapUnavailable):
        await client.public_festivals_monthly(year=2026, month=3, page_size=12)
    await client.public_festivals_monthly(year=2026, month=3, page_size=12)
    assert len(sent) == 4
    # 짧게만 — TTL이 지나면 다시 부른다.
    clock.now += 301
    await client.public_festivals_monthly(year=2026, month=1, page_size=12)
    assert len(sent) == 5
    await client.aclose()


async def test_cached_month_is_a_copy_callers_cannot_mutate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"months": [], "items": [{"feature_id": "f_a"}]}, "meta": {}},
        )

    client = _client(handler)
    first = await client.public_festivals_monthly(year=2026, month=5)
    first["items"].clear()
    again = await client.public_festivals_monthly(year=2026, month=5)
    assert again["items"] == [{"feature_id": "f_a"}]
    await client.aclose()


AsyncHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _async_client(handler: AsyncHandler) -> KorTravelMapClient:
    http = httpx.AsyncClient(
        base_url="http://map.test", transport=httpx.MockTransport(handler), timeout=5.0
    )
    return KorTravelMapClient(
        http, max_attempts=3, backoff_base_seconds=0.0, service_token="svc-token-secret"
    )


async def test_concurrent_requests_for_one_cold_month_reach_map_once() -> None:
    sent = 0
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        await release.wait()
        return httpx.Response(200, json=_MONTHLY)

    client = _async_client(handler)
    calls = [
        asyncio.create_task(client.public_festivals_monthly(year=2026, month=1)) for _ in range(6)
    ]
    await asyncio.sleep(0)
    release.set()
    pages = await asyncio.gather(*calls)
    assert sent == 1
    assert all(page == pages[0] for page in pages)
    await client.aclose()


async def test_single_flight_failure_reaches_every_waiter_and_is_not_cached() -> None:
    sent = 0
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        await release.wait()
        raise httpx.ReadTimeout("cold month", request=request)

    client = _async_client(handler)
    calls = [
        asyncio.create_task(client.public_festivals_monthly(year=2026, month=2)) for _ in range(3)
    ]
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*calls, return_exceptions=True)
    assert sent == 1
    assert all(isinstance(r, KorTravelMapUnavailable) for r in results)
    await client.aclose()


async def test_cold_months_cannot_take_the_shared_slots_from_search() -> None:
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/public/festivals/monthly":
            await release.wait()
            return httpx.Response(200, json=_MONTHLY)
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _async_client(handler)
    slow = [
        asyncio.create_task(client.public_festivals_monthly(year=2026, month=month))
        for month in range(1, FESTIVALS_MAX_CONCURRENT_REQUESTS + 1)
    ]
    await asyncio.sleep(0)
    # 축제 자리가 다 찼다 — 다음 축제 월은 바로 거부되고, 검색은 그대로 Map에 닿는다.
    with pytest.raises(KorTravelMapUnavailable) as info:
        await client.public_festivals_monthly(year=2026, month=12)
    assert info.value.code == "BULKHEAD_FULL"
    assert (await client.search_features(q="안동하회마을"))["items"] == []
    release.set()
    await asyncio.gather(*slow)
    await client.aclose()
