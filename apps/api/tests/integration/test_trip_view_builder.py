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

    async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
        self.requested_ids = list(feature_ids)
        return {
            "found": {
                "place:abc123": {
                    "feature_id": "place:abc123",
                    "name": "최신 경복궁",
                    "marker_color": "P-01",
                    "marker_icon": "monument",
                }
            },
            "missing": [],
        }


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
            email=f"builder_{uuid.uuid4().hex[:8]}@pinvi.test",
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

        kor_travel_map_client = _StringFeatureClient()
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=kor_travel_map_client)

    assert kor_travel_map_client.requested_ids == ["place:abc123"]
    assert view["broken_feature_count"] == 0
    built_poi = view["days"][0]["pois"][0]
    assert built_poi["feature_id"] == "place:abc123@raw"
    assert built_poi["title"] == "최신 경복궁"
    assert built_poi["rise_set"]["status"] == "success"
    assert built_poi["rise_set"]["locdate"] == date(2026, 5, 6)
    assert built_poi["rise_set"]["sunrise_at"] == datetime(2026, 5, 6, 5, 30, tzinfo=UTC)


async def test_build_trip_view_skips_null_feature_ids(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"null_feature_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="자유 장소 여행")
        db.add_all([trip, TripDay(trip_id=trip_id, day_index=1, title="1일차")])
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id=None,
                feature_snapshot={"name": "지도 밖 메모 장소"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
        await db.refresh(trip)

        kor_travel_map_client = _StringFeatureClient()
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=kor_travel_map_client)

    assert kor_travel_map_client.requested_ids == []
    assert view["broken_feature_count"] == 0
    built_poi = view["days"][0]["pois"][0]
    assert built_poi["feature_id"] is None
    assert built_poi["title"] == "지도 밖 메모 장소"


async def test_build_trip_view_includes_public_holidays(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.kasi import KasiSpecialDay
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"holiday_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="공휴일 여행")
        db.add_all(
            [
                trip,
                TripDay(trip_id=trip_id, day_index=1, date=date(2026, 8, 15), title="광복절"),
                TripDay(trip_id=trip_id, day_index=2, date=date(2026, 8, 16), title="둘째 날"),
                KasiSpecialDay(
                    dataset="holidays",
                    sol_date=date(2026, 8, 15),
                    name="광복절",
                    sequence="1",
                    is_holiday=True,
                ),
                KasiSpecialDay(
                    dataset="anniversaries",
                    sol_date=date(2026, 8, 15),
                    name="광복절 기념일",
                    sequence="2",
                    is_holiday=False,
                ),
            ]
        )
        await db.commit()
        await db.refresh(trip)

        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)

    assert view["days"][0]["holidays"] == [
        {"date": date(2026, 8, 15), "name": "광복절", "dataset": "holidays"}
    ]
    assert view["days"][1]["holidays"] == []


async def test_build_trip_view_day_presentation(session_factory) -> None:  # type: ignore[no-untyped-def]
    """ADR-055: effective_date 파생 + out_of_range + 일자색/display 색."""
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"pres_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        # 2일 여행. day 3은 기간 밖(파생 effective_date로 검증). date는 모두 override 없음(NULL).
        trip = Trip(
            trip_id=trip_id,
            owner_user_id=user_id,
            title="표시 모델",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 11),
        )
        db.add_all(
            [
                trip,
                TripDay(trip_id=trip_id, day_index=1, marker_color="P-10"),  # 색 override
                TripDay(trip_id=trip_id, day_index=2),  # override 없음 → 기본 P-02
                TripDay(trip_id=trip_id, day_index=3),  # 기간 밖
            ]
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id=None,
                    feature_snapshot={"name": "커스텀 색"},
                    custom_marker_color="P-05",
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a1",
                    feature_id=None,
                    feature_snapshot={"name": "일자색 상속"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=2,
                    sort_order="a0",
                    feature_id=None,
                    feature_snapshot={"name": "기본 일자색"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
            ]
        )
        await db.commit()
        await db.refresh(trip)

        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)

    days = {d["day_index"]: d for d in view["days"]}
    assert days[1]["date"] is None
    assert days[1]["effective_date"] == date(2026, 6, 10)
    assert days[1]["out_of_range"] is False
    assert days[1]["marker_color"] == "P-10"
    assert days[2]["effective_date"] == date(2026, 6, 11)
    assert days[2]["marker_color"] is None
    assert days[3]["effective_date"] == date(2026, 6, 12)
    assert days[3]["out_of_range"] is True

    # POI display_marker_color: custom(POI) > 일자 override > 일자 기본색.
    assert days[1]["pois"][0]["display_marker_color"] == "P-05"  # POI custom
    assert days[1]["pois"][1]["display_marker_color"] == "P-10"  # day1 override 상속
    assert days[2]["pois"][0]["display_marker_color"] == "P-02"  # day2 기본색


class _CountingFeatureClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.last_requested: list[str] = []

    async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
        self.call_count += 1
        self.last_requested = list(feature_ids)
        return {
            "found": {
                "place:cache1": {
                    "feature_id": "place:cache1",
                    "name": "캐시된 장소",
                    "marker_color": "P-02",
                }
            },
            "missing": [],
        }


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
                email=f"cache_{uuid.uuid4().hex[:8]}@pinvi.test",
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
        first = await build_trip_view(db, trip=trip, kor_travel_map_client=client)
        second = await build_trip_view(db, trip=trip, kor_travel_map_client=client)

    # 1번째는 fetch, 2번째는 캐시 hit → get_features 추가 호출 없음.
    assert client.call_count == 1
    assert first["days"][0]["pois"][0]["title"] == "캐시된 장소"
    assert second["days"][0]["pois"][0]["title"] == "캐시된 장소"
