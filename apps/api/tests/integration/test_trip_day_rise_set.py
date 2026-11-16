"""해·달 출몰을 응답 때 계산한다(astral) — 저장 표·동기화 없음(0109, 2026-11-17).

일자 rise/set = 그 일자 POI centroid, 장소 rise/set = 그 장소 좌표. 종전 일자·장소 출몰 표와 그 동기화는
은퇴했다. 동기화 경합 시험들은 대상이 없어 지웠고, 단일 커넥션 풀·권한 경합 회귀는 그대로 남긴다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User

pytestmark = pytest.mark.asyncio

KST = ZoneInfo("Asia/Seoul")


def _hm(value: Any) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return str(value.astimezone(KST).strftime("%H:%M"))


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


async def _trip_owner_and_poi(session_factory: Any, trip_id: uuid.UUID) -> tuple[str, str]:
    async with session_factory() as db:
        owner = await db.scalar(select(Trip.owner_user_id).where(Trip.trip_id == trip_id))
        poi = await db.scalar(select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id))
    return str(owner), str(poi)


async def test_build_trip_view_computes_sun_and_moon(session_factory: Any) -> None:
    from app.services.trip_view_builder import build_trip_view

    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)
    days = {d["day_index"]: d for d in view["days"]}
    # 부산 2026-06-10 KASI 고시 일출 05:09 · 일몰 19:37. 달 출몰도 astral(같은 날짜의 사건).
    day1 = days[1]["rise_set"]
    assert day1["status"] == "success"
    assert (_hm(day1["sunrise_at"]), _hm(day1["sunset_at"])) == ("05:09", "19:37")
    assert (_hm(day1["moonrise_at"]), _hm(day1["moonset_at"])) == ("01:12", "14:07")
    assert day1["moonrise_at"].astimezone(KST).date() == date(2026, 6, 10)
    assert day1["fetched_at"] is None
    assert days[1]["rise_set_reference"] == "광안리 해수욕장"
    assert days[2]["rise_set"]["status"] == "pending_coord"
    assert days[2]["rise_set"]["moonrise_at"] is None
    poi = days[1]["pois"][0]
    assert poi["rise_set"]["status"] == "success"
    assert poi["rise_set"]["sunrise_at"] == day1["sunrise_at"]
    assert poi["rise_set"]["moonrise_at"] == day1["moonrise_at"]


async def test_kasi_rise_set_tables_are_gone(session_factory: Any) -> None:
    async with session_factory() as db:
        for table in ("trip_day_rise_sets", "trip_poi_rise_sets"):
            assert await db.scalar(text(f"SELECT to_regclass('app.{table}')")) is None


async def test_moving_a_poi_recomputes_both_days_without_writes(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    trip_id = await _seed_trip_with_poi(session_factory)
    owner, poi_id = await _trip_owner_and_poi(session_factory, trip_id)
    moved = await client.patch(
        f"/trips/{trip_id}/pois/{poi_id}",
        headers={"If-Match": "1"},
        json={"day_index": 2},
        cookies=auth_cookies(owner),
    )
    assert moved.status_code == 200, moved.text
    rise = moved.json()["data"]["rise_set"]
    # 이동한 날(2026-06-11)의 값으로 바로 계산한다.
    assert rise["status"] == "success" and rise["locdate"] == "2026-06-11"
    assert (_hm(rise["moonrise_at"]), _hm(rise["moonset_at"])) == ("01:40", "15:16")
    view = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner))
    assert view.status_code == 200, view.text
    days = {d["day_index"]: d for d in view.json()["data"]["days"]}
    assert days[1]["rise_set"]["status"] == "pending_coord"
    assert days[2]["rise_set"]["status"] == "success"
    assert days[2]["rise_set_reference"] == "광안리 해수욕장"


async def test_get_and_move_do_not_exhaust_single_connection_pool(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    _database_url: str,
) -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db import session as db_session
    from app.db.session import SESSION_TIMEOUT_SERVER_SETTINGS

    trip_id = await _seed_trip_with_poi(session_factory)
    owner, poi_id = await _trip_owner_and_poi(session_factory, trip_id)
    engine = create_async_engine(
        _database_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        connect_args={"server_settings": SESSION_TIMEOUT_SERVER_SETTINGS},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "async_session_factory", factory)
    try:
        for method, path, kwargs in [
            ("GET", f"/trips/{trip_id}", {}),
            (
                "PATCH",
                f"/trips/{trip_id}/pois/{poi_id}",
                {"headers": {"If-Match": "1"}, "json": {"day_index": 2}},
            ),
            ("GET", f"/trips/{trip_id}", {}),
        ]:
            response = await asyncio.wait_for(
                client.request(method, path, cookies=auth_cookies(owner), **kwargs),
                timeout=5,
            )
            assert response.status_code == 200, response.text
        final = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner))
        days = {d["day_index"]: d for d in final.json()["data"]["days"]}
        assert days[2]["rise_set"]["status"] == "success"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("method", ["DELETE", "PATCH"])
async def test_delayed_poi_write_cannot_follow_admin_move_into_another_users_trip(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    import asyncio

    import app.services.poi as poi_service

    trip_id = await _seed_trip_with_poi(session_factory)
    target_id = await _seed_trip_with_poi(session_factory)
    owner, poi_id = await _trip_owner_and_poi(session_factory, trip_id)
    target_owner, _ = await _trip_owner_and_poi(session_factory, target_id)
    assert owner != target_owner
    async with session_factory() as db:
        admin = User(
            email="admin684@pinvi.test",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        admin_id = str(admin.user_id)
    original_lock = poi_service._lock_active_trip
    observed = asyncio.Event()
    resume = asyncio.Event()

    async def delayed_lock(db: Any, source_id: uuid.UUID) -> Any:
        observed.set()
        await asyncio.wait_for(resume.wait(), timeout=10)
        return await original_lock(db, source_id)

    monkeypatch.setattr(poi_service, "_lock_active_trip", delayed_lock)
    # 관리자 이동 뒤 버전(2)을 추측해도 기존 여행의 권한만으로 PATCH할 수 없어야 한다.
    kwargs = (
        {"headers": {"If-Match": "2"}, "json": {"user_note": "타인 여행에 쓰면 안 됨"}}
        if method == "PATCH"
        else {}
    )
    pending = asyncio.create_task(
        client.request(
            method,
            f"/trips/{trip_id}/pois/{poi_id}",
            cookies=auth_cookies(owner),
            **kwargs,
        )
    )
    try:
        await asyncio.wait_for(observed.wait(), timeout=5)
        moved = await client.post(
            f"/admin/pois/{poi_id}/move",
            cookies=auth_cookies(admin_id),
            json={
                "target_trip_id": str(target_id),
                "target_day_index": 2,
                "attachment_policy": "move",
                "comment_policy": "move",
                "access_reason": "권한 경합 회귀 시험",
            },
        )
        assert moved.status_code == 200, moved.text
    finally:
        resume.set()
        response = await asyncio.wait_for(pending, timeout=5)
    assert response.status_code == 404, response.text
    async with session_factory() as db:
        poi = await db.get(TripDayPoi, uuid.UUID(poi_id))
        assert poi is not None and poi.trip_id == target_id
        assert poi.deleted_at is None and poi.user_note is None and poi.version == 2
