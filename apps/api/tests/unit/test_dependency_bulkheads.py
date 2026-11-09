"""의존 서비스·표면별 동시 호출 상한(bulkhead) (#621).

Map client는 회로를 표면별로 나눴지만(#702) 동시 호출 자리는 하나(16)였다. 느린 viewport·weather가 그
자리를 다 쓰면 상세·검색·trip view까지 `BULKHEAD_FULL` 503이 됐다. 자리도 회로와 같은 단위로 나눈다.
Telegram은 상한이 없어 정지 때 쓰기 트랜잭션을 쥔 요청이 timeout(5초)까지 쌓였다.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapUnavailable

_SLOW_PATHS = {
    "viewport": "/v1/features/in-bounds",
    "transport": "/v1/service/transport/",
    "weather": "/v1/service/weather/",
}


def _sample(provider: str, scope: str) -> float:
    from app.clients._resilience import BULKHEAD_REJECTIONS

    return BULKHEAD_REJECTIONS.labels(provider=provider, scope=scope)._value.get()


def _map(handler: Any, **kwargs: Any) -> KorTravelMapClient:
    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler))
    return KorTravelMapClient(
        http, service_token="fixture", max_attempts=1, backoff_base_seconds=0.0, **kwargs
    )


async def _call_surface(client: KorTravelMapClient, surface: str) -> Any:
    if surface == "viewport":
        return await client.features_in_bounds(
            min_lon=128.0, min_lat=36.0, max_lon=129.0, max_lat=37.0, zoom=9
        )
    if surface == "transport":
        from app.clients.kor_travel_map_transport import KorTravelMapTransportClient

        return await KorTravelMapTransportClient(client).list_items(
            "fuel-stations", bbox=(128.0, 36.0, 129.0, 37.0)
        )
    from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient

    return await KorTravelMapWeatherClient(client).nearest(lon=126.9, lat=37.5)


@pytest.mark.parametrize("slow_surface", ["viewport", "transport", "weather"])
async def test_slow_surface_cannot_take_feature_slots(slow_surface: str) -> None:
    release = asyncio.Event()
    started = 0
    all_started = asyncio.Event()
    slow_prefix = _SLOW_PATHS[slow_surface]

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal started
        if request.url.path.startswith(slow_prefix):
            started += 1
            if started == 2:
                all_started.set()
            await release.wait()
            return httpx.Response(
                200, json={"data": {"items": [], "clusters": []}, "meta": {}}
            )
        return httpx.Response(200, json={"data": {"feature_id": "f_x"}, "meta": {}})

    client = _map(handler, max_concurrent_requests=2)
    slow = [asyncio.create_task(_call_surface(client, slow_surface)) for _ in range(2)]
    try:
        await asyncio.wait_for(all_started.wait(), 2)
        before = _sample("kor_travel_map", slow_surface)
        # 느린 표면은 자기 자리가 찼다 — 다음 호출은 Map에 보내지 않고 바로 거부한다.
        with pytest.raises(Exception) as info:
            await asyncio.wait_for(_call_surface(client, slow_surface), 0.5)
        # transport는 Map 예외를 감싸 code를 버린다(공개 사유는 UPSTREAM_UNAVAILABLE) — 원인에서 본다.
        rejected = info.value if slow_surface != "transport" else info.value.__cause__
        assert getattr(rejected, "code", None) == "BULKHEAD_FULL"
        assert started == 2
        assert _sample("kor_travel_map", slow_surface) == before + 1
        # 상세(features 자리)는 그대로 Map에 닿는다 — 자리 두 개를 모두 쓸 수 있다.
        details = await asyncio.wait_for(
            asyncio.gather(client.get_feature("f_x"), client.get_feature("f_x")), 1
        )
        assert details == [{"feature_id": "f_x"}, {"feature_id": "f_x"}]
    finally:
        release.set()
        await asyncio.gather(*slow, return_exceptions=True)
        await client.aclose()


async def test_full_feature_surface_rejects_without_sending_and_returns_capacity() -> None:
    release = asyncio.Event()
    sent = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        await release.wait()
        return httpx.Response(200, json={"data": {"feature_id": "f_x"}, "meta": {}})

    client = _map(handler, max_concurrent_requests=16, surface_concurrency={"features": 1})
    held = asyncio.create_task(client.get_feature("f_x"))
    try:
        await asyncio.sleep(0.01)
        with pytest.raises(KorTravelMapUnavailable) as info:
            await asyncio.wait_for(client.get_feature("f_x"), 0.5)
        assert info.value.code == "BULKHEAD_FULL"
        assert sent == 1
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)
        release.set()
        assert await client.get_feature("f_x") == {"feature_id": "f_x"}
        assert sent == 2
    finally:
        release.set()
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)
        await client.aclose()


def test_surface_concurrency_rejects_unknown_scope_and_non_positive_limit() -> None:
    http = httpx.AsyncClient(base_url="http://map.test")
    with pytest.raises(ValueError):
        KorTravelMapClient(http, surface_concurrency={"nope": 1})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        KorTravelMapClient(http, surface_concurrency={"viewport": 0})


async def test_factories_take_caps_from_settings() -> None:
    from app.clients.kor_travel_geo import create_kor_travel_geo_client
    from app.clients.kor_travel_map import create_kor_travel_map_client
    from app.clients.kor_travel_weather import create_kor_travel_weather_client
    from app.core.config import Settings

    app_settings = Settings(
        pinvi_kor_travel_map_features_max_concurrency=11,
        pinvi_kor_travel_map_viewport_max_concurrency=7,
        pinvi_kor_travel_map_transport_max_concurrency=3,
        pinvi_kor_travel_map_weather_max_concurrency=2,
        pinvi_kor_travel_geo_max_concurrency=5,
        pinvi_kor_travel_weather_max_concurrency=6,
    )
    map_client = create_kor_travel_map_client(app_settings)
    geo = create_kor_travel_geo_client(app_settings)
    weather = create_kor_travel_weather_client(app_settings)
    try:
        assert map_client._bulkhead_limits == {
            "features": 11,
            "viewport": 7,
            "transport": 3,
            "festivals": 4,
            "weather": 2,
        }
        assert geo._slots._value == 5
        assert weather._slots._value == 6
    finally:
        await map_client._http.aclose()
        await geo.aclose()
        await weather.aclose()


def test_default_caps_are_bounded() -> None:
    from app.core.config import Settings

    defaults = Settings()
    assert defaults.pinvi_database_max_overflow == 5
    assert defaults.pinvi_database_pool_timeout_seconds <= 5
    # Map 표면 합계가 예전 공용 자리(16)를 크게 넘지 않게 — weather·transport는 작은 몫이다.
    assert defaults.pinvi_kor_travel_map_features_max_concurrency == 12
    assert defaults.pinvi_kor_travel_map_viewport_max_concurrency == 8
    assert defaults.pinvi_kor_travel_map_transport_max_concurrency == 4
    assert defaults.pinvi_kor_travel_map_weather_max_concurrency == 4
    assert defaults.pinvi_kor_travel_geo_max_concurrency == 8
    assert defaults.pinvi_kor_travel_weather_max_concurrency == 8
    assert defaults.pinvi_telegram_max_concurrency == 4


async def test_telegram_cap_is_process_wide_fails_fast_and_returns_capacity() -> None:
    from app.clients.telegram import TelegramClient, TelegramError

    release = asyncio.Event()
    sent = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        await release.wait()
        return httpx.Response(200, json={"ok": True, "result": {"id": 1, "type": "private"}})

    def make() -> TelegramClient:
        # 운영처럼 요청마다 새 client — 상한은 인스턴스가 아니라 worker 전체에 걸린다.
        http = httpx.AsyncClient(
            base_url="https://telegram.test", transport=httpx.MockTransport(handler)
        )
        return TelegramClient(http, timeout_seconds=2.0, max_concurrent_requests=2)

    clients = [make() for _ in range(4)]
    held = [
        asyncio.create_task(clients[i].verify_target("123:" + "a" * 30, "-100")) for i in range(2)
    ]
    try:
        await asyncio.sleep(0.01)
        assert sent == 2
        before = _sample("telegram", "all")
        with pytest.raises(TelegramError) as info:
            await asyncio.wait_for(clients[2].verify_target("123:" + "a" * 30, "-100"), 0.5)
        assert info.value.code == "network_error"
        assert sent == 2
        assert _sample("telegram", "all") == before + 1
        # 취소된 호출도 자리를 돌려준다.
        held[0].cancel()
        await asyncio.gather(held[0], return_exceptions=True)
        release.set()
        await held[1]
        await clients[3].verify_target("123:" + "a" * 30, "-100")
        assert sent == 3
        assert TelegramClient._in_flight == 0
    finally:
        release.set()
        for task in held:
            task.cancel()
        await asyncio.gather(*held, return_exceptions=True)
        for item in clients:
            await item.aclose()
