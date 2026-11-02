"""외부 호출 동안 요청 세션이 풀 커넥션을 쥐지 않는다 (2026-11-02 점검, 복원력 수정 3).

요청 세션은 인증 조회부터 요청 끝까지 트랜잭션을 연 채 커넥션을 쥐었다. Map·weather 호출
(수 초~수십 초) 동안 그 커넥션이 idle-in-transaction으로 묶여, 동시 요청이 늘면 다른
엔드포인트가 풀 대기에 걸린다. 외부 호출 시점에 세션이 트랜잭션 밖이어야 한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

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
