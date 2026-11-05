"""실제 소유 PG에서 직접 resolve 요청/배경 경계를 검증한다."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest

from app.clients.kor_travel_weather import (
    CoordinateRequestOut,
    LocationOut,
    ResolvedWeatherOut,
)
from app.models.user import User
from app.services.weather_location_resolver import resolve_weather_location


def resolved(lat: float, lon: float, location_id: str = "fixture") -> ResolvedWeatherOut:
    location = LocationOut(
        location_id=location_id,
        name="fixture",
        latitude=lat,
        longitude=lon,
        enabled=True,
    )
    return ResolvedWeatherOut(
        requested=CoordinateRequestOut(latitude=lat, longitude=lon),
        location=location,
        distance_km=0.1,
        source_locations=(location,),
    )


async def close_if_available(client: Any) -> None:
    try:
        module = importlib.import_module("app.services.weather_resolve_worker")
    except ModuleNotFoundError:
        return
    await module.close_weather_resolve_worker(client)


async def test_request_miss_returns_while_provider_is_still_blocked(session_factory) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    class Provider:
        async def resolve(self, *, lat, lon, **_kwargs):
            entered.set()
            await release.wait()
            return resolved(lat, lon)

    provider = Provider()
    async with session_factory() as db:
        task = asyncio.create_task(
            resolve_weather_location(
                db,
                feature_id="nonblocking",
                lat=37.5,
                lon=127.0,
                client=provider,
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.sleep(0)
            assert task.done(), "request is waiting for provider resolve"
            assert type(task.result()).__name__ == "WeatherLocationPending"
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            await close_if_available(provider)


async def test_request_miss_does_not_commit_callers_unrelated_write(
    session_factory,
    verified_user,
) -> None:
    class Provider:
        async def resolve(self, *, lat, lon, **_kwargs):
            return resolved(lat, lon)

    provider = Provider()
    async with session_factory() as db:
        import uuid

        user = await db.get(User, uuid.UUID(verified_user[0]))
        before = user.nickname
        user.nickname = "caller-uncommitted"
        await resolve_weather_location(
            db,
            feature_id="no-commit",
            lat=37.5,
            lon=127.0,
            client=provider,
        )
        await db.rollback()
    await close_if_available(provider)
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(verified_user[0]))
        assert user.nickname == before, "resolver committed the caller's unrelated write"


async def test_fill_uses_separate_session_and_caller_deadline_is_not_inherited(session_factory):
    from app.clients.kor_travel_weather import _call_scope, kor_travel_weather_call_deadline
    from app.models.weather_location_link import WeatherLocationLink
    from app.services.weather_location_resolver import WeatherLocationFound, WeatherLocationPending
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    seen = []

    class Provider:
        async def resolve(self, *, lat, lon, read_timeout_seconds, **_kwargs):
            seen.append((_call_scope.get(), read_timeout_seconds))
            await asyncio.sleep(0.03)
            return resolved(lat, lon)

    provider = Provider()
    try:
        with kor_travel_weather_call_deadline(asyncio.get_running_loop().time() + 0.001):
            async with session_factory() as db:
                result = await resolve_weather_location(
                    db,
                    feature_id="separate",
                    lat=37.5,
                    lon=127,
                    client=provider,
                )
                assert isinstance(result, WeatherLocationPending)
        await get_weather_resolve_worker(provider).drain()
        assert seen == [(None, 45.0)]
        async with session_factory() as db:
            hit = await resolve_weather_location(
                db,
                feature_id="separate",
                lat=37.5,
                lon=127,
                client=provider,
            )
            assert isinstance(hit, WeatherLocationFound)
            assert await db.get(WeatherLocationLink, "separate") is not None
    finally:
        await close_if_available(provider)


async def test_no_data_and_failure_negative_cache_expire_without_repeated_requests(session_factory):
    from app.clients.kor_travel_weather import KorTravelWeatherNotFound, KorTravelWeatherUnavailable
    from app.services.weather_location_resolver import WeatherLocationNoData, WeatherLocationPending
    from app.services.weather_resolve_worker import _WORKERS, WeatherResolveWorker

    now = [0.0]

    class Provider:
        def __init__(self):
            self.calls = 0
            self.mode = "no_data"

        async def resolve(self, *, lat, lon, **_kwargs):
            self.calls += 1
            if self.mode == "no_data":
                raise KorTravelWeatherNotFound("fixture", status_code=404)
            raise KorTravelWeatherUnavailable("fixture")

    provider = Provider()
    worker = WeatherResolveWorker(provider, session_factory=session_factory, clock=lambda: now[0])
    _WORKERS[provider] = worker
    try:

        async def request():
            async with session_factory() as db:
                return await resolve_weather_location(
                    db,
                    feature_id="negative",
                    lat=37.5,
                    lon=127,
                    client=provider,
                )

        assert isinstance(await request(), WeatherLocationPending)
        await worker.drain()
        assert provider.calls == 3
        assert isinstance(await request(), WeatherLocationNoData)
        assert provider.calls == 3
        now[0] = 31
        provider.mode = "failure"
        assert isinstance(await request(), WeatherLocationPending)
        await worker.drain()
        assert provider.calls == 4
        assert isinstance(await request(), WeatherLocationPending)
        assert provider.calls == 4
        now[0] = 62
        await request()
        await worker.drain()
        assert provider.calls == 5
    finally:
        await close_if_available(provider)


async def test_same_feature_singleflight_coalesces_coordinates_and_rejects_old_result(
    session_factory,
):
    from app.models.weather_location_link import WeatherLocationLink
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    entered, release = asyncio.Event(), asyncio.Event()

    class Provider:
        def __init__(self):
            self.calls = []
            self.active = 0
            self.peak = 0

        async def resolve(self, *, lat, lon, **_kwargs):
            self.calls.append(lat)
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                if len(self.calls) == 1:
                    entered.set()
                    await release.wait()
                return resolved(lat, lon, str(lat))
            finally:
                self.active -= 1

    provider = Provider()
    try:

        async def request(lat):
            async with session_factory() as db:
                await resolve_weather_location(
                    db,
                    feature_id="coalesce",
                    lat=lat,
                    lon=127,
                    client=provider,
                )

        await request(37)
        await asyncio.wait_for(entered.wait(), 1)
        for _ in range(3):
            await request(37)
        await request(38)
        await request(39)
        release.set()
        await get_weather_resolve_worker(provider).drain()
        assert provider.calls == [37, 39]
        assert provider.peak == 1
        async with session_factory() as db:
            row = await db.get(WeatherLocationLink, "coalesce")
            assert row.lat == 39
            assert row.location_id == "39"
    finally:
        release.set()
        await close_if_available(provider)


@pytest.mark.parametrize("change", ["map", "delete", "coordinates", "flag"])
async def test_late_completion_cannot_overwrite_changed_or_deleted_cache(
    session_factory,
    monkeypatch,
    change,
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete, update

    from app.core.config import settings
    from app.models.weather_location_link import WeatherLocationLink
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    entered, release = asyncio.Event(), asyncio.Event()

    class Provider:
        async def resolve(self, *, lat, lon, **_kwargs):
            entered.set()
            await release.wait()
            return resolved(lat, lon, "late-direct")

    provider = Provider()
    async with session_factory() as db:
        db.add(
            WeatherLocationLink(
                feature_id="fenced",
                location_id="old",
                source_location_ids=["old"],
                lat=37,
                lon=127,
                distance_km=0,
                measurement_point=None,
                resolved_at=datetime.now(UTC),
                stale=True,
            )
        )
        await db.commit()
    try:
        async with session_factory() as db:
            await resolve_weather_location(
                db,
                feature_id="fenced",
                lat=37,
                lon=127,
                client=provider,
            )
        await asyncio.wait_for(entered.wait(), 1)
        async with session_factory() as db:
            if change == "delete":
                await db.execute(
                    delete(WeatherLocationLink).where(WeatherLocationLink.feature_id == "fenced")
                )
            elif change == "flag":
                monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", True)
            else:
                await db.execute(
                    update(WeatherLocationLink)
                    .where(WeatherLocationLink.feature_id == "fenced")
                    .values(
                        location_id="new-owner",
                        lat=38 if change == "coordinates" else 37,
                        measurement_point={"resolved_via": "kor_travel_map"}
                        if change == "map"
                        else None,
                        updated_at=datetime.now(UTC) + timedelta(seconds=1),
                    )
                )
            await db.commit()
        release.set()
        await get_weather_resolve_worker(provider).drain()
        async with session_factory() as db:
            row = await db.get(WeatherLocationLink, "fenced")
            if change == "delete":
                assert row is None
            elif change == "flag":
                assert row.location_id == "old"
            else:
                assert row.location_id == "new-owner"
    finally:
        release.set()
        await close_if_available(provider)


async def test_worker_queue_concurrency_and_shutdown_are_bounded(session_factory):
    from app.services.weather_resolve_worker import WeatherResolveWorker

    entered, release = asyncio.Event(), asyncio.Event()

    class Provider:
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.calls = 0

        async def resolve(self, *, lat, lon, **_kwargs):
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == 2:
                entered.set()
            try:
                await release.wait()
                return resolved(lat, lon)
            finally:
                self.active -= 1

    provider = Provider()
    worker = WeatherResolveWorker(provider, session_factory=session_factory, capacity=2)
    for i in range(2):
        worker.schedule(feature_id=str(i), lat=37, lon=127, radii_km=(20,), row=None)
    await asyncio.wait_for(entered.wait(), 1)
    for i in range(2, 20):
        worker.schedule(feature_id=str(i), lat=37, lon=127, radii_km=(20,), row=None)
    assert worker._queue.qsize() == 2
    assert len(worker._latest) == 4
    await asyncio.wait_for(worker.close(), 1)
    assert provider.peak == 2
    assert provider.active == 0
    assert worker._queue.qsize() == 0
    assert worker._latest == {}
    worker.schedule(feature_id="closed", lat=37, lon=127, radii_km=(20,), row=None)
    assert provider.calls == 2


async def test_coordinate_change_during_commit_rebases_only_the_workers_own_result(session_factory):
    from app.models.weather_location_link import WeatherLocationLink
    from app.services.weather_resolve_worker import _WORKERS, WeatherResolveWorker

    committing, release = asyncio.Event(), asyncio.Event()

    class Provider:
        async def resolve(self, *, lat, lon, **_kwargs):
            return resolved(lat, lon, str(lat))

    class SessionProxy:
        commits = 0

        def __init__(self):
            self.session = session_factory()

        async def __aenter__(self):
            await self.session.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.session.__aexit__(*args)

        async def execute(self, *args):
            return await self.session.execute(*args)

        async def commit(self):
            type(self).commits += 1
            if type(self).commits == 1:
                committing.set()
                await release.wait()
            await self.session.commit()

        async def rollback(self):
            await self.session.rollback()

    provider = Provider()
    worker = WeatherResolveWorker(provider, session_factory=SessionProxy)
    _WORKERS[provider] = worker
    try:
        async with session_factory() as db:
            await resolve_weather_location(
                db,
                feature_id="commit-coord",
                lat=37,
                lon=127,
                client=provider,
            )
        await asyncio.wait_for(committing.wait(), 1)
        async with session_factory() as db:
            await resolve_weather_location(
                db,
                feature_id="commit-coord",
                lat=38,
                lon=127,
                client=provider,
            )
        release.set()
        await worker.drain()
        async with session_factory() as db:
            row = await db.get(WeatherLocationLink, "commit-coord")
            assert row.lat == 38, "new coordinates were lost while old cache result committed"
    finally:
        release.set()
        await close_if_available(provider)


async def test_owned_http_slow_resolve_fills_cache_after_first_response_without_inherited_deadline(
    session_factory,
):
    import dataclasses
    import json

    import httpx

    from app.clients.kor_travel_weather import (
        KorTravelWeatherClient,
        kor_travel_weather_call_deadline,
    )
    from app.services.weather_location_resolver import WeatherLocationFound, WeatherLocationPending
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    entered, release = asyncio.Event(), asyncio.Event()
    connections = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        connections.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            entered.set()
            await release.wait()
            body = json.dumps(
                {"data": dataclasses.asdict(resolved(37.5, 127)), "meta": {}}
            ).encode()
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            connections.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=0.02)
    provider = KorTravelWeatherClient(http, max_attempts=1)
    try:
        with kor_travel_weather_call_deadline(asyncio.get_running_loop().time() + 0.001):
            async with session_factory() as db:
                first = await resolve_weather_location(
                    db,
                    feature_id="owned-http-fill",
                    lat=37.5,
                    lon=127,
                    client=provider,
                )
        assert isinstance(first, WeatherLocationPending)
        await asyncio.wait_for(entered.wait(), 1)
        # shared read=20ms를 넘기는 실제 TCP 대기지만 resolve 전용45초와 독립 context는 유지된다.
        await asyncio.sleep(0.04)
        release.set()
        await asyncio.wait_for(get_weather_resolve_worker(provider).drain(), 2)
        async with session_factory() as db:
            result = await resolve_weather_location(
                db,
                feature_id="owned-http-fill",
                lat=37.5,
                lon=127,
                client=provider,
            )
        assert isinstance(result, WeatherLocationFound)
        assert result.location_id == "fixture"
        assert http.timeout.read == 0.02
    finally:
        release.set()
        await close_if_available(provider)
        await provider.aclose()
        server.close()
        await server.wait_closed()
        if connections:
            await asyncio.wait_for(asyncio.gather(*connections), 2)


async def test_row_created_by_map_after_cold_miss_is_not_overwritten(session_factory):
    from datetime import UTC, datetime

    from app.models.weather_location_link import WeatherLocationLink
    from app.services.weather_resolve_worker import get_weather_resolve_worker

    entered, release = asyncio.Event(), asyncio.Event()

    class Provider:
        async def resolve(self, *, lat, lon, **_kwargs):
            entered.set()
            await release.wait()
            return resolved(lat, lon, "late-direct")

    provider = Provider()
    try:
        async with session_factory() as db:
            await resolve_weather_location(
                db,
                feature_id="map-created",
                lat=37,
                lon=127,
                client=provider,
            )
        await asyncio.wait_for(entered.wait(), 1)
        async with session_factory() as db:
            db.add(
                WeatherLocationLink(
                    feature_id="map-created",
                    location_id="new-map",
                    source_location_ids=["new-map"],
                    lat=37,
                    lon=127,
                    distance_km=0,
                    measurement_point={"resolved_via": "kor_travel_map"},
                    resolved_at=datetime.now(UTC),
                    stale=False,
                )
            )
            await db.commit()
        release.set()
        await get_weather_resolve_worker(provider).drain()
        async with session_factory() as db:
            row = await db.get(WeatherLocationLink, "map-created")
            assert row.location_id == "new-map"
            assert row.measurement_point == {"resolved_via": "kor_travel_map"}
    finally:
        release.set()
        await close_if_available(provider)
