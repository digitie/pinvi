"""Trip 상세 view builder feature_id 계약 회귀 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


class _StringFeatureClient:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []

    async def features_by_ids(self, feature_ids: list[str]) -> list[dict[str, Any]]:
        self.requested_ids = list(feature_ids)
        return [
            {
                "feature_id": "place:abc123",
                "title": "최신 경복궁",
                "marker_color": "P-01",
                "marker_icon": "monument",
            }
        ]


async def test_build_trip_view_batches_opaque_feature_ids(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.kasi import TripPoiRiseSet
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        user = User(
            user_id=user_id,
            email=f"builder_{uuid.uuid4().hex[:8]}@tripmate.test",
            status="active",
            email_verified_at=now,
        )
        db.add(user)
        await db.flush()

        trip = Trip(
            trip_id=trip_id,
            owner_user_id=user_id,
            title="서울 여행",
        )
        day = TripDay(trip_id=trip_id, day_index=1, title="1일차")
        db.add_all([trip, day])
        await db.flush()

        poi = TripDayPoi(
            trip_id=trip_id,
            day_index=1,
            sort_order="a0",
            feature_id="place:abc123@raw",
            feature_snapshot={"title": "저장된 경복궁"},
            added_by_user_id=user_id,
            currency="KRW",
        )
        db.add(poi)
        await db.flush()
        db.add(
            TripPoiRiseSet(
                poi_id=poi.attachment_id,
                locdate=date(2026, 5, 6),
                status="success",
                sunrise_at=datetime(2026, 5, 6, 5, 30, tzinfo=UTC),
                sunset_at=datetime(2026, 5, 6, 19, 30, tzinfo=UTC),
            )
        )
        await db.commit()
        await db.refresh(trip)

        krtour_client = _StringFeatureClient()
        view = await build_trip_view(db, trip=trip, krtour_client=krtour_client)

    assert krtour_client.requested_ids == ["place:abc123"]
    assert view["broken_feature_count"] == 0
    built_poi = view["days"][0]["pois"][0]
    assert built_poi["feature_id"] == "place:abc123@raw"
    assert built_poi["title"] == "최신 경복궁"
    assert built_poi["rise_set"]["status"] == "success"
    assert built_poi["rise_set"]["locdate"] == date(2026, 5, 6)
    assert built_poi["rise_set"]["sunrise_at"] == datetime(2026, 5, 6, 5, 30, tzinfo=UTC)


class _CountingFeatureClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.last_requested: list[str] = []

    async def features_by_ids(self, feature_ids: list[str]) -> list[dict[str, Any]]:
        self.call_count += 1
        self.last_requested = list(feature_ids)
        return [{"feature_id": "place:cache1", "title": "캐시된 장소", "marker_color": "P-02"}]


async def test_build_trip_view_uses_feature_cache(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    feature_cache.clear()
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"cache_{uuid.uuid4().hex[:8]}@tripmate.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        db.add_all(
            [
                Trip(trip_id=trip_id, owner_user_id=user_id, title="캐시 여행"),
                TripDay(trip_id=trip_id, day_index=1, title="1일차"),
            ]
        )
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id="place:cache1@raw",
                feature_snapshot={"title": "저장본"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
        await db.refresh(trip := await db.get(Trip, trip_id))

        client = _CountingFeatureClient()
        first = await build_trip_view(db, trip=trip, krtour_client=client)
        second = await build_trip_view(db, trip=trip, krtour_client=client)

    # 1번째는 fetch, 2번째는 캐시 hit → features_by_ids 추가 호출 없음.
    assert client.call_count == 1
    assert first["days"][0]["pois"][0]["title"] == "캐시된 장소"
    assert second["days"][0]["pois"][0]["title"] == "캐시된 장소"
