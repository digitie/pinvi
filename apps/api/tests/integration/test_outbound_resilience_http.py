"""소유 loopback HTTP와 실제 PG에서 provider 격리·회로·관측을 함께 검증한다."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from app.clients.kor_travel_geo import KorTravelGeoClient, KorTravelGeoUnavailable
from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapUnavailable
from app.clients.kor_travel_weather import KorTravelWeatherClient, KorTravelWeatherUnavailable
from app.middleware.api_call_logging import (
    ApiCallLoggingClient,
    api_call_event_hooks,
    close_api_call_logs,
)
from app.models.api_call_log import ApiCallLog


@pytest.mark.parametrize("provider", ["map", "geo", "weather"])
async def test_real_http_saturation_timeout_trial_and_log_batch(session_factory, provider) -> None:
    received = asyncio.Event()
    healthy = False
    requests = 0
    connections = set()
    now = [0.0]

    async def handle(reader, writer):
        nonlocal requests
        task = asyncio.current_task()
        connections.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            requests += 1
            received.set()
            if healthy:
                payload = (
                    {"status": "ok", "candidates": []}
                    if provider == "geo"
                    else {"data": [] if provider == "weather" else {}, "meta": {}}
                )
                body = json.dumps(payload).encode()
                writer.write(
                    f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
            else:
                await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            connections.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http = ApiCallLoggingClient(
        base_url=f"http://127.0.0.1:{port}",
        timeout=1.0,
        event_hooks=api_call_event_hooks(session_factory, provider=provider),
    )
    kwargs = {"max_attempts": 1, "max_concurrent_requests": 1, "clock": lambda: now[0]}
    if provider == "map":
        client = KorTravelMapClient(http, **kwargs)
        error = KorTravelMapUnavailable

        async def call():
            return await client.get_feature("fixture")
    elif provider == "geo":
        client = KorTravelGeoClient(http, api_key="fixture-private", **kwargs)
        error = KorTravelGeoUnavailable

        async def call():
            return await client.geocode(query="fixture")
    else:
        client = KorTravelWeatherClient(http, **kwargs)
        error = KorTravelWeatherUnavailable

        async def call():
            return await client.latest("fixture")

    pending = asyncio.create_task(call())
    try:
        await asyncio.wait_for(received.wait(), 2)
        with pytest.raises(error, match="동시 호출 상한"):
            await asyncio.wait_for(call(), 0.1)
        assert requests == 1
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        http.timeout = httpx.Timeout(0.03)
        for _ in range(3):
            with pytest.raises(error):
                await call()
        now[0] = 31.0
        with pytest.raises(error, match="회로 열림"):
            await call()
        assert requests == 4

        now[0] = 120.0
        healthy = True
        await call()
        assert requests == 5
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.aclose()
        await close_api_call_logs(session_factory)
        server.close()
        await server.wait_closed()
        if connections:
            await asyncio.wait_for(asyncio.gather(*connections), 2)

    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(ApiCallLog)
                    .where(ApiCallLog.provider == provider)
                    .order_by(ApiCallLog.log_id)
                )
            ).all()
        )
    assert [row.error_class for row in rows] == [
        "CancelledError",
        "ReadTimeout",
        "ReadTimeout",
        "ReadTimeout",
        None,
    ]
    assert "fixture-private" not in repr([row.endpoint for row in rows])
