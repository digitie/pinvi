"""일자 rise/set sync + build_trip_view emit 통합 테스트 (ADR-055 §6, T-305)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.models.kasi import TripDayRiseSet
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.services.trip_day_rise_set import sync_trip_day_rise_sets

pytestmark = pytest.mark.asyncio


async def _seed_trip_with_poi(session_factory: Any, *, with_coord: bool = True) -> uuid.UUID:
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"rs_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        db.add_all(
            [
                Trip(
                    trip_id=trip_id,
                    owner_user_id=user_id,
                    title="일출 여행",
                    start_date=date(2026, 6, 10),
                    end_date=date(2026, 6, 11),
                ),
                TripDay(trip_id=trip_id, day_index=1),
                TripDay(trip_id=trip_id, day_index=2),
            ]
        )
        await db.flush()
        snapshot: dict[str, Any] = {"name": "광안리 해수욕장"}
        if with_coord:
            snapshot["coord"] = {"lon": 129.118, "lat": 35.153}
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id=None,
                feature_snapshot=snapshot,
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
    return trip_id


async def test_sync_creates_day_rise_set_rows(session_factory: Any) -> None:
    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        await sync_trip_day_rise_sets(db, trip_id=trip_id)
    async with session_factory() as db:
        rows = {
            r.day_index: r
            for r in await db.scalars(
                select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id)
            )
        }
    # day1: POI 좌표 있음 → pending_fetch + 기준 좌표/라벨.
    assert rows[1].status == "pending_fetch"
    assert rows[1].locdate == date(2026, 6, 10)
    assert round(rows[1].longitude or 0, 3) == 129.118
    assert rows[1].reference_label == "광안리 해수욕장"
    # day2: POI 없음 → pending_coord(좌표 앵커 없음), locdate는 파생.
    assert rows[2].status == "pending_coord"
    assert rows[2].locdate == date(2026, 6, 11)


async def test_sync_marks_stale_when_coord_changes(session_factory: Any) -> None:
    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        await sync_trip_day_rise_sets(db, trip_id=trip_id)
    # ETL이 채운 것처럼 success로 만든 뒤 좌표를 바꾸면 stale + pending_fetch로 표시돼야 한다.
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
        assert row is not None
        row.status = "success"
        row.stale = False
        poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.trip_id == trip_id, TripDayPoi.day_index == 1)
        )
        assert poi is not None
        poi.feature_snapshot = {"name": "다른 장소", "coord": {"lon": 127.0, "lat": 37.5}}
        await db.commit()
    async with session_factory() as db:
        await sync_trip_day_rise_sets(db, trip_id=trip_id)
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
    assert row is not None
    assert row.stale is True
    assert row.status == "pending_fetch"
    assert round(row.longitude or 0, 3) == 127.0


async def test_build_trip_view_emits_day_rise_set(session_factory: Any) -> None:
    from app.services.trip_view_builder import build_trip_view

    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        await sync_trip_day_rise_sets(db, trip_id=trip_id)
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)
    days = {d["day_index"]: d for d in view["days"]}
    assert days[1]["rise_set"]["status"] == "pending_fetch"
    assert days[1]["rise_set_reference"] == "광안리 해수욕장"
    assert days[2]["rise_set"]["status"] == "pending_coord"
