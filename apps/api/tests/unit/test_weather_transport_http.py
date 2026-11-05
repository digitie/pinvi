"""소유 loopback HTTP·실제 httpx 연결 풀로 weather 전송 시점을 검증한다."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherDeadlineExhausted,
    kor_travel_weather_call_deadline,
)


async def test_pool_wait_before_send_does_not_count_as_remote_deadline_failure() -> None:
    held = asyncio.Event()
    release_hold = asyncio.Event()
    handlers: set[asyncio.Task[Any]] = set()
    trace_events: list[str] = []
    weather_requests = 0
    healthy = False

    async def prior_trace(name: str, info: dict[str, Any]) -> None:
        trace_events.append(name)

    class TracedClient(httpx.AsyncClient):
        def build_request(self, *args: Any, **kwargs: Any) -> httpx.Request:
            request = super().build_request(*args, **kwargs)
            request.extensions["trace"] = prior_trace
            return request

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal weather_requests
        task = asyncio.current_task()
        assert task is not None
        handlers.add(task)
        try:
            while True:
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                except asyncio.IncompleteReadError:
                    return
                path = headers.split(b" ", 2)[1]
                if path == b"/hold":
                    held.set()
                    await release_hold.wait()
                else:
                    weather_requests += 1
                    if not healthy:
                        # 응답을 기다리는 client가 deadline에 연결을 닫을 때까지 대기한다.
                        await reader.read()
                        return
                body = json.dumps({"data": [], "meta": {}}).encode()
                writer.write(
                    f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
                )
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http = TracedClient(
        base_url=f"http://127.0.0.1:{port}",
        timeout=httpx.Timeout(0.4, pool=1.0),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    )
    client = KorTravelWeatherClient(http, max_attempts=1)
    holds: list[asyncio.Task[httpx.Response]] = []
    try:
        for _ in range(3):
            held.clear()
            release_hold.clear()
            hold = asyncio.create_task(http.get("/hold"))
            holds.append(hold)
            await asyncio.wait_for(held.wait(), 1)

            async def free_pool_later() -> None:
                # 총 예산은 read의 절반보다 크지만 실제 전송 때 남은 예산은 훨씬 작다.
                await asyncio.sleep(0.23)
                release_hold.set()

            free_pool = asyncio.create_task(free_pool_later())
            try:
                deadline = asyncio.get_running_loop().time() + 0.32
                with kor_travel_weather_call_deadline(deadline):
                    with pytest.raises(KorTravelWeatherDeadlineExhausted):
                        await client.latest("fixture")
            finally:
                await free_pool
                await hold
        assert weather_requests == 3
        healthy = True
        assert await client.latest("fixture") == ()
        assert weather_requests == 4
        # 기존 trace callback이 새 계측과 함께 호출되고 keep-alive 재사용도 유지된다.
        assert trace_events.count("http11.send_request_headers.started") == 7
    finally:
        release_hold.set()
        for hold in holds:
            hold.cancel()
        await asyncio.gather(*holds, return_exceptions=True)
        await client.aclose()
        server.close()
        await server.wait_closed()
        for task in list(handlers):
            task.cancel()
        await asyncio.gather(*list(handlers), return_exceptions=True)
