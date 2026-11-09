"""느린 외부 의존이 DB 풀을 고갈시키거나 상관없는 엔드포인트를 막지 못한다 (#621).

운영 근거: pool 10/overflow 0이 Map 정지 동안 한 번 고갈됐다(정상 peak 7). 외부 호출을 기다리는 요청이
읽기 트랜잭션을 연 채 커넥션을 쥐면, 동시 요청 수만큼 풀이 묶이고 DB만 쓰는 엔드포인트까지 풀 대기
(`pool_timeout`) 뒤 실패한다. 여기서는 실제 queue pool(크기 2, overflow 0)을 앱에 꽂고 풀 크기보다
많은 요청을 느린 의존에 붙잡아 둔 채, 풀이 비어 있고 DB 전용 엔드포인트가 바로 응답하는지 본다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db_pool import ObservedAsyncQueuePool

pytestmark = pytest.mark.asyncio

_POOL_SIZE = 2
_HELD_REQUESTS = 6  # 풀 크기의 세 배 — 하나라도 커넥션을 쥐면 풀이 고갈된다.


class _Gate:
    """느린 의존: 호출을 세고, 풀어 줄 때까지 붙잡는다."""

    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.entered = 0
        self.all_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def hold(self) -> None:
        self.entered += 1
        if self.entered >= self.expected:
            self.all_entered.set()
        await self.release.wait()


@pytest_asyncio.fixture
async def pooled_app(session_factory, monkeypatch) -> AsyncIterator[AsyncEngine]:  # type: ignore[no-untyped-def]
    """앱 전역 세션 팩토리를 작은 실제 queue pool로 바꾼다(conftest 기본은 NullPool)."""
    import app.db.session as db_session
    import app.middleware.location_audit as loc_audit
    from app.core.config import settings

    engine = create_async_engine(
        settings.pinvi_database_url,
        pool_size=_POOL_SIZE,
        max_overflow=0,
        pool_timeout=0.5,
        poolclass=ObservedAsyncQueuePool,
        connect_args={"server_settings": db_session.SESSION_TIMEOUT_SERVER_SETTINGS},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "async_session_factory", factory)
    monkeypatch.setattr(loc_audit, "async_session_factory", factory)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _assert_pool_free_and_unrelated_endpoint_fast(
    client: Any, engine: AsyncEngine, cookies: dict[str, str], gate: _Gate
) -> None:
    await asyncio.wait_for(gate.all_entered.wait(), 5)
    # 모든 요청이 느린 의존 안에서 기다리는 중이다 — 어느 것도 풀 커넥션을 쥐지 않는다.
    assert engine.pool.checkedout() == 0
    # DB만 쓰는 상관없는 엔드포인트는 풀 대기 없이 바로 응답한다.
    unrelated = await asyncio.wait_for(client.get("/users/me/telegram-targets", cookies=cookies), 3)
    assert unrelated.status_code == 200, unrelated.text


async def test_slow_geo_with_device_consent_does_not_hold_pool_connections(
    pooled_app, client, verified_user, auth_cookies, grant_location_consent
) -> None:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.main import app

    user_id, _ = verified_user
    await grant_location_consent(user_id)
    gate = _Gate(_HELD_REQUESTS)

    class _SlowGeo:
        async def reverse(self, **_kwargs: Any) -> dict[str, Any]:
            await gate.hold()
            return {"status": "ok", "candidates": [{"region": {"sig_cd": "26500"}}]}

    app.dependency_overrides[get_kor_travel_geo_client] = _SlowGeo
    cookies = auth_cookies(user_id)
    held = [
        asyncio.create_task(
            client.get(
                "/regions/covering-point?lon=129.1&lat=35.1&coord_source=device"
                if index % 2
                else "/geo/reverse?lon=129.1&lat=35.1&coord_source=device",
                cookies=cookies,
            )
        )
        for index in range(_HELD_REQUESTS)
    ]
    try:
        await _assert_pool_free_and_unrelated_endpoint_fast(client, pooled_app, cookies, gate)
        gate.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*held), 5)
        assert [r.status_code for r in responses] == [200] * _HELD_REQUESTS
    finally:
        gate.release.set()
        await asyncio.gather(*held, return_exceptions=True)
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)


async def test_slow_map_nearby_does_not_hold_consent_dependency_connection(
    pooled_app, client, verified_user, auth_cookies, grant_location_consent
) -> None:
    """`/features/nearby`는 동의를 dependency로 검사한 뒤 Map을 부른다(리뷰 P1)."""
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.main import app
    from app.services.category_labels import reset_category_label_cache

    reset_category_label_cache()
    user_id, _ = verified_user
    await grant_location_consent(user_id)
    gate = _Gate(_HELD_REQUESTS)

    class _SlowMap:
        async def features_nearby(self, **_kwargs: Any) -> dict[str, Any]:
            await gate.hold()
            return {"items": []}

        async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
            return {"items": []}

    app.dependency_overrides[get_kor_travel_map_client] = _SlowMap
    cookies = auth_cookies(user_id)
    held = [
        asyncio.create_task(
            client.get("/features/nearby?lon=129.1&lat=35.1&radius_m=500", cookies=cookies)
        )
        for _ in range(_HELD_REQUESTS)
    ]
    try:
        await _assert_pool_free_and_unrelated_endpoint_fast(client, pooled_app, cookies, gate)
        gate.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*held), 5)
        assert [r.status_code for r in responses] == [200] * _HELD_REQUESTS
    finally:
        gate.release.set()
        await asyncio.gather(*held, return_exceptions=True)
        app.dependency_overrides.pop(get_kor_travel_map_client, None)
        reset_category_label_cache()


@pytest.mark.parametrize("slow", ["map", "kakao"])
async def test_slow_search_dependency_does_not_hold_pool_connections(
    pooled_app, client, verified_user, auth_cookies, grant_location_consent, slow
) -> None:
    from app.clients.kakao_local import get_kakao_local_client
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.clients.naver_local import get_naver_local_client
    from app.main import app
    from app.services.category_labels import reset_category_label_cache

    reset_category_label_cache()
    user_id, _ = verified_user
    await grant_location_consent(user_id)
    gate = _Gate(_HELD_REQUESTS)

    class _Map:
        async def search_features(self, **_kwargs: Any) -> dict[str, Any]:
            if slow == "map":
                await gate.hold()
            return {"items": [], "next_cursor": None}

        async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
            return {"items": []}

    class _Geo:
        async def search(self, **_kwargs: Any) -> dict[str, Any]:
            return {"status": "ok", "candidates": []}

    class _Kakao:
        async def search_keyword(self, **_kwargs: Any) -> dict[str, Any]:
            if slow == "kakao":
                await gate.hold()
            return {"documents": []}

    overrides = {
        get_kor_travel_map_client: _Map,
        get_kor_travel_geo_client: _Geo,
        get_kakao_local_client: _Kakao,
        get_naver_local_client: lambda: None,
    }
    app.dependency_overrides.update(overrides)
    cookies = auth_cookies(user_id)
    # lat/lon = "내 주변 검색": 위치 동의를 조회한 뒤 Map·geo, 내 POI 조회 뒤 Kakao를 부른다.
    held = [
        asyncio.create_task(client.get("/search?q=광안리&lat=35.15&lon=129.12", cookies=cookies))
        for _ in range(_HELD_REQUESTS)
    ]
    try:
        await _assert_pool_free_and_unrelated_endpoint_fast(client, pooled_app, cookies, gate)
        gate.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*held), 5)
        assert [r.status_code for r in responses] == [200] * _HELD_REQUESTS
    finally:
        gate.release.set()
        await asyncio.gather(*held, return_exceptions=True)
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        reset_category_label_cache()


async def test_admin_role_dependency_ends_read_transaction(session_factory) -> None:  # type: ignore[no-untyped-def]
    """관리자 proxy(Map admin·Dagster)도 외부 호출 동안 역할 조회 트랜잭션을 쥐지 않는다."""
    from app.core.rbac import require_role
    from app.models.user import User

    user_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"pool_admin_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                roles=["admin"],
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.commit()

    async with session_factory() as db:
        user = await require_role("admin")(str(user_id), db)
        assert user.user_id == user_id
        assert db.in_transaction() is False
        # expire_on_commit=False — 이미 읽은 사용자 객체는 그대로 쓸 수 있다.
        assert user.roles == ["admin"]
