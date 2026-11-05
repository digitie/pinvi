"""실제 소유 PG/API/loopback HTTP에서 cold 카드→배경 해석→warm 카드를 확인한다."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.clients.kor_travel_map import get_kor_travel_map_client
from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    get_optional_kor_travel_weather_client,
)
from app.core.config import settings
from app.middleware.api_call_logging import (
    ApiCallLoggingClient,
    api_call_event_hooks,
    close_api_call_logs,
)
from app.models.api_call_log import ApiCallLog
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_resolve_worker import (
    close_weather_resolve_worker,
    get_weather_resolve_worker,
)


async def test_public_cold_card_warms_off_request_with_long_resolve_timeout(
    client,
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch,
) -> None:
    from app.main import app

    monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", False)
    release = asyncio.Event()
    entered = asyncio.Event()
    tasks = set()
    paths = []
    stamp = datetime.now(UTC).isoformat()
    location = {
        "location_id": "fixture-location",
        "name": "fixture",
        "latitude": 37.5,
        "longitude": 127.0,
        "enabled": True,
    }
    value = {
        "value_id": "fixture-value",
        "location_id": "fixture-location",
        "provider": "python-kma-api",
        "dataset_key": "fixture",
        "weather_domain": "weather",
        "forecast_style": "observed",
        "metric_key": "TEMP",
        "value_number": 21.0,
        "unit": "deg_c",
        "target_at": stamp,
        "known_at": stamp,
        "collected_at": stamp,
        "normalization_version": "fixture-v1",
        "source_record_key": "fixture-record",
    }

    async def serve(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            path = request.split(b" ", 2)[1].decode().split("?", 1)[0]
            paths.append(path)
            if path == "/v1/weather/resolve":
                entered.set()
                await release.wait()
                data = {
                    "requested": {"latitude": 37.5, "longitude": 127.0},
                    "location": location,
                    "source_locations": [location],
                    "distance_km": 0.1,
                }
            elif path.endswith("/latest"):
                data = [value]
            else:
                data = []
            body = json.dumps({"data": data, "meta": {}}).encode()
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http = ApiCallLoggingClient(
        base_url=f"http://127.0.0.1:{port}",
        timeout=0.02,
        event_hooks=api_call_event_hooks(session_factory, provider="owned_weather_background"),
    )
    weather = KorTravelWeatherClient(http, max_attempts=1)

    class Map:
        async def get_feature(self, feature_id):
            return {"feature_id": feature_id, "kind": "place", "lon": 127.0, "lat": 37.5}

    app.dependency_overrides[get_kor_travel_map_client] = Map
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather
    try:
        for _ in range(2):
            response = await asyncio.wait_for(
                client.get(
                    "/features/fixture-background/weather", cookies=auth_cookies(verified_user[0])
                ),
                1,
            )
            assert response.status_code == 200
            assert response.json()["data"]["metrics"] == []
        await asyncio.wait_for(entered.wait(), 1)
        # 기본 read 20ms보다 오래 멈춰도 요청은 이미 끝났고 배경 resolve는 45초 상한을 쓴다.
        await asyncio.sleep(0.05)
        assert paths.count("/v1/weather/resolve") == 1
        release.set()
        await asyncio.wait_for(get_weather_resolve_worker(weather).drain(), 2)
        async with session_factory() as db:
            cached = await db.get(WeatherLocationLink, "fixture-background")
            assert cached is not None
            assert cached.source_location_ids == ["fixture-location"]
        warm = await client.get(
            "/features/fixture-background/weather", cookies=auth_cookies(verified_user[0])
        )
        assert warm.status_code == 200
        metrics = warm.json()["data"]["metrics"]
        assert [(item["metric_key"], item["value_number"]) for item in metrics] == [("T1H", 21.0)]
        assert paths.count("/v1/weather/resolve") == 1
    finally:
        release.set()
        app.dependency_overrides.pop(get_kor_travel_map_client, None)
        app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)
        await close_weather_resolve_worker(weather)
        await weather.aclose()
        await close_api_call_logs(session_factory)
        server.close()
        await server.wait_closed()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(ApiCallLog).where(ApiCallLog.provider == "owned_weather_background")
                )
            ).all()
        )
    assert len(rows) == 3
    assert all(row.status_code == 200 and row.error_class is None for row in rows)
