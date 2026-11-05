"""외부 호출 동안 요청 세션이 풀 커넥션을 쥐지 않는다 (2026-11-02 점검, 복원력 수정 3).

요청 세션은 인증 조회부터 요청 끝까지 트랜잭션을 연 채 커넥션을 쥐었다. Map·weather 호출
(수 초~수십 초) 동안 그 커넥션이 idle-in-transaction으로 묶여, 동시 요청이 늘면 다른
엔드포인트가 풀 대기에 걸린다. 외부 호출 시점에 세션이 트랜잭션 밖이어야 한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.clients.kor_travel_map import FeatureBatchItem, FeatureTripCard, FoundFeatureBatchItem

pytestmark = pytest.mark.asyncio


async def _seed_user(db: AsyncSession) -> uuid.UUID:
    from app.models.user import User

    user_id = uuid.uuid4()
    db.add(
        User(
            user_id=user_id,
            email=f"release_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return user_id


async def test_auth_dependency_ends_read_transaction(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.core.deps import get_current_user_id
    from app.core.security import create_access_token

    async with session_factory() as db:
        user_id = await _seed_user(db)

    async with session_factory() as db:
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        resolved = await get_current_user_id(
            request, db, pinvi_access=create_access_token(subject=str(user_id))
        )
        assert resolved == str(user_id)
        assert db.in_transaction() is False


class _TransactionProbeFeatureClient:
    """get_features가 불리는 순간 세션이 트랜잭션 안인지 기록한다."""

    def __init__(self, db: AsyncSession, feature_id: str) -> None:
        self._db = db
        self._feature_id = feature_id
        self.in_transaction_at_call: bool | None = None

    async def get_features(
        self,
        feature_ids: list[str],
        *,
        known_row_revisions: Mapping[str, int] | None = None,
    ) -> dict[str, FeatureBatchItem]:
        self.in_transaction_at_call = self._db.in_transaction()
        return {
            self._feature_id: FoundFeatureBatchItem(
                feature_id=self._feature_id,
                row_revision=1,
                trip_card=FeatureTripCard(
                    feature_id=self._feature_id,
                    kind="place",
                    name="도산서원",
                    category="heritage",
                    lon=128.84,
                    lat=36.728,
                    address={"road_address": "경상북도 안동시"},
                    marker_icon="monument",
                    marker_color="P-01",
                ),
            )
        }


async def test_release_keeps_transaction_when_writes_were_flushed(session_factory) -> None:  # type: ignore[no-untyped-def]
    """리뷰: flush된 쓰기는 new/dirty로 안 보인다 — 그때 커밋하면 호출자의 커밋 시점을 앞당긴다."""
    from app.db.session import release_read_connection
    from app.models.user import User

    user_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"flushed_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.flush()
        await release_read_connection(db)
        assert db.in_transaction() is True
        await db.rollback()

    async with session_factory() as db:
        assert await db.get(User, user_id) is None


async def test_flushed_writes_flag_clears_when_the_transaction_ends(session_factory) -> None:  # type: ignore[no-untyped-def]
    """flush 표시는 그 트랜잭션에서만 — 커밋 뒤의 읽기 트랜잭션은 다시 닫혀야 한다(소유자 trip view는
    rise/set 동기화가 flush·커밋한 뒤 view를 만든다)."""
    from app.db.session import release_read_connection
    from app.models.user import User

    async with session_factory() as db:
        db.add(
            User(
                user_id=uuid.uuid4(),
                email=f"flag_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.flush()
        await db.commit()
        await db.get(User, uuid.uuid4())
        assert db.in_transaction() is True
        await release_read_connection(db)
        assert db.in_transaction() is False


async def test_weather_card_does_not_wait_or_multiply_hanging_background_resolves(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    """냉미스 카드는 배경 resolve를 기다리지 않고 같은 feature를 한 번만 예약한다."""
    import asyncio

    import httpx

    from app.clients.kor_travel_weather import KorTravelWeatherClient
    from app.services.weather_card import resolve_and_collect_deduped_values
    from app.services.weather_resolve_worker import close_weather_resolve_worker

    calls = 0
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path != "/v1/weather/resolve":
            return httpx.Response(200, json={"data": [], "meta": {}}, request=request)
        calls += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        return httpx.Response(200, request=request)

    client = KorTravelWeatherClient(
        httpx.AsyncClient(
            base_url="http://kor-travel-weather.test",
            transport=httpx.MockTransport(hang),
            timeout=httpx.Timeout(4.0, connect=0.2),
        ),
        max_attempts=3,
        backoff_base_seconds=0.0,
        max_concurrent_requests=1,
    )
    try:
        for _ in range(4):
            async with session_factory() as db:
                values, _known = await resolve_and_collect_deduped_values(
                    db,
                    feature_id="place:hang@raw",
                    lat=36.728,
                    lon=128.84,
                    asof=None,
                    weather_client=client,
                    budget_seconds=1.0,
                )
                assert db.in_transaction() is False
            assert values == []
            assert not cleaned.is_set(), "card deadline cancelled the background resolve"
        await asyncio.wait_for(entered.wait(), 1)
        assert calls == 1
        await close_weather_resolve_worker(client)
        assert cleaned.is_set()
        # 배경 취소가 provider 자리나 회로를 누수시키지 않는다.
        assert await client.latest("loc-release") == ()
    finally:
        await close_weather_resolve_worker(client)
        await client.aclose()


class _ProbeWeatherClient:
    """resolve·latest가 불리는 순간 세션이 트랜잭션 안인지 기록한다."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self.in_transaction: dict[str, bool] = {}

    async def resolve(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> Any:
        from app.clients.kor_travel_weather import (
            CoordinateRequestOut,
            LocationOut,
            ResolvedWeatherOut,
        )

        assert read_timeout_seconds == 45.0
        self.in_transaction["resolve"] = self._db.in_transaction()
        location = LocationOut(
            location_id="loc-release", name="안동", latitude=lat, longitude=lon, enabled=True
        )
        return ResolvedWeatherOut(
            requested=CoordinateRequestOut(latitude=lat, longitude=lon),
            location=location,
            distance_km=0.1,
            measurement_point=None,
            source_locations=(location,),
        )

    async def latest(self, location_id: str, *, limit: int | None = None) -> tuple[Any, ...]:
        self.in_transaction["latest"] = self._db.in_transaction()
        return ()

    async def forecast(self, location_id: str, **_: Any) -> tuple[Any, ...]:
        self.in_transaction["forecast"] = self._db.in_transaction()
        return ()


async def test_weather_card_ends_read_transaction_before_weather_calls(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    """냉미스 배경 해석과 적중 후 latest/forecast 모두 요청의 읽기 커넥션을 반환한다."""
    from app.services.weather_card import resolve_and_collect_deduped_values
    from app.services.weather_resolve_worker import (
        close_weather_resolve_worker,
        get_weather_resolve_worker,
    )

    feature_id = f"place:wx{uuid.uuid4().hex[:8]}@raw"
    async with session_factory() as db:
        client = _ProbeWeatherClient(db)
        try:
            values, _known = await resolve_and_collect_deduped_values(
                db,
                feature_id=feature_id,
                lat=36.728,
                lon=128.84,
                asof=None,
                weather_client=client,  # type: ignore[arg-type]
            )
            assert values == []
            assert db.in_transaction() is False
            await get_weather_resolve_worker(client).drain()  # type: ignore[arg-type]
            assert client.in_transaction == {"resolve": False}
        except BaseException:
            await close_weather_resolve_worker(client)  # type: ignore[arg-type]
            raise
    try:
        async with session_factory() as db:
            client._db = db
            await resolve_and_collect_deduped_values(
                db,
                feature_id=feature_id,
                lat=36.728,
                lon=128.84,
                asof=None,
                weather_client=client,  # type: ignore[arg-type]
            )
            assert db.in_transaction() is False
        assert client.in_transaction == {"resolve": False, "latest": False, "forecast": False}
    finally:
        await close_weather_resolve_worker(client)  # type: ignore[arg-type]


async def test_trip_view_ends_read_transaction_before_map_call(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    feature_cache.clear()
    feature_id = f"place:release{uuid.uuid4().hex[:8]}@raw"
    async with session_factory() as db:
        user_id = await _seed_user(db)
        trip = Trip(trip_id=uuid.uuid4(), owner_user_id=user_id, title="안동 여행")
        db.add(trip)
        await db.flush()
        db.add(TripDay(trip_id=trip.trip_id, day_index=1, title="1일차"))
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip.trip_id,
                day_index=1,
                sort_order="a0",
                feature_id=feature_id,
                feature_snapshot={"title": "도산서원"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()

    async with session_factory() as db:
        loaded = await db.get(Trip, trip.trip_id)
        assert loaded is not None
        client = _TransactionProbeFeatureClient(db, feature_id)
        view = await build_trip_view(db, trip=loaded, kor_travel_map_client=client)

    assert view["days"][0]["pois"][0]["feature_resolution_state"] == "found"
    assert client.in_transaction_at_call is False
