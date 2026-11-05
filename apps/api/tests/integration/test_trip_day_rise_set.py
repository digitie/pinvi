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
        await sync_trip_day_rise_sets(trip_id=trip_id)
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
        await sync_trip_day_rise_sets(trip_id=trip_id)
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
        await sync_trip_day_rise_sets(trip_id=trip_id)
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
        await sync_trip_day_rise_sets(trip_id=trip_id)
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)
    days = {d["day_index"]: d for d in view["days"]}
    assert days[1]["rise_set"]["status"] == "pending_fetch"
    assert days[1]["rise_set_reference"] == "광안리 해수욕장"
    assert days[2]["rise_set"]["status"] == "pending_coord"


async def test_maintenance_failure_preserves_loaded_trip_and_poi(
    session_factory: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from sqlalchemy import inspect, text
    from sqlalchemy.ext.asyncio import AsyncSession

    trip_id = await _seed_trip_with_poi(session_factory)
    original_execute = AsyncSession.execute

    async def fail_cache_write(db: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if str(statement).startswith("INSERT INTO app.trip_day_rise_sets"):
            return await original_execute(
                db, text("SELECT CAST('fixture-private-sql-param' AS int)")
            )
        return await original_execute(db, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", fail_cache_write)
    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        poi = await db.scalar(select(TripDayPoi).where(TripDayPoi.trip_id == trip_id))
        assert trip is not None and poi is not None
        await sync_trip_day_rise_sets(trip_id=trip_id)
        assert not inspect(trip).expired
        assert not inspect(poi).expired
        assert trip.title == "일출 여행"
        assert poi.day_index == 1
    assert "fixture-private-sql-param" not in caplog.text


@pytest.mark.parametrize("flushed", [False, True])
async def test_sync_does_not_commit_or_rollback_caller_writes(
    session_factory: Any, flushed: bool
) -> None:
    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        owner_id = trip.owner_user_id
        user = await db.get(User, owner_id)
        assert user is not None
        user.nickname = "아직 커밋하지 않은 변경"
        if flushed:
            await db.flush()
        await sync_trip_day_rise_sets(trip_id=trip_id)
        assert user.nickname == "아직 커밋하지 않은 변경"
        async with session_factory() as observer:
            assert (
                await observer.scalar(select(User.nickname).where(User.user_id == owner_id)) is None
            )
        await db.rollback()
    async with session_factory() as observer:
        assert await observer.scalar(select(User.nickname).where(User.user_id == owner_id)) is None


async def _trip_owner_and_poi(session_factory: Any, trip_id: uuid.UUID) -> tuple[str, str]:
    async with session_factory() as db:
        owner = await db.scalar(select(Trip.owner_user_id).where(Trip.trip_id == trip_id))
        poi = await db.scalar(select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id))
    return str(owner), str(poi)


async def test_concurrent_gets_atomically_create_one_cache_row_per_day(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    trip_id = await _seed_trip_with_poi(session_factory)
    owner, _ = await _trip_owner_and_poi(session_factory, trip_id)
    original_scalar = AsyncSession.scalar
    ready = asyncio.Event()
    contenders: set[int] = set()

    async def concurrent_lock(db: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            "FROM app.trips" in str(statement)
            and "FOR UPDATE" in str(statement)
            and id(db) not in contenders
        ):
            contenders.add(id(db))
            if len(contenders) == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=5)
        return await original_scalar(db, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", concurrent_lock)
    responses = await asyncio.wait_for(
        asyncio.gather(
            client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner)),
            client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner)),
        ),
        timeout=10,
    )
    assert len(contenders) == 2
    assert [response.status_code for response in responses] == [200, 200]
    for response in responses:
        assert len(response.json()["data"]["days"]) == 2
        assert response.json()["data"]["days"][0]["rise_set"]["status"] == "pending_fetch"
    async with session_factory() as db:
        rows = list(
            await db.scalars(select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id))
        )
    assert sorted(row.day_index for row in rows) == [1, 2]
    assert "trip_day_rise_set.sync_failed" not in caplog.text


async def test_cache_db_failure_preserves_get_and_committed_poi_move(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    trip_id = await _seed_trip_with_poi(session_factory)
    owner, poi_id = await _trip_owner_and_poi(session_factory, trip_id)
    original_execute = AsyncSession.execute

    async def fail_cache_insert(db: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if str(statement).startswith("INSERT INTO app.trip_day_rise_sets"):
            return await original_execute(
                db, text("SELECT CAST('fixture-private-sql-param' AS int)")
            )
        return await original_execute(db, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", fail_cache_insert)
    got = await client.get(f"/trips/{trip_id}", cookies=auth_cookies(owner))
    assert got.status_code == 200, got.text
    assert got.json()["data"]["trip"]["title"] == "일출 여행"
    moved = await client.patch(
        f"/trips/{trip_id}/pois/{poi_id}",
        cookies=auth_cookies(owner),
        headers={"If-Match": "1"},
        json={"day_index": 2},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["day_index"] == 2
    assert moved.json()["data"]["version"] == 2
    async with session_factory() as db:
        poi = await db.get(TripDayPoi, uuid.UUID(poi_id))
        assert poi is not None and poi.day_index == 2
        assert (
            list(await db.scalars(select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id)))
            == []
        )
    warnings = [r for r in caplog.records if r.message == "trip_day_rise_set.sync_failed"]
    assert len(warnings) == 2
    assert all(r.error_type == "DBAPIError" for r in warnings)
    assert "fixture-private-sql-param" not in caplog.text


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
        async with factory() as db:
            rows = list(
                await db.scalars(select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id))
            )
        assert len(rows) == 2
        assert next(row for row in rows if row.day_index == 2).status == "pending_fetch"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("flushed", [False, True])
async def test_get_skips_maintenance_when_caller_has_pending_writes(
    session_factory: Any, flushed: bool
) -> None:
    from app.api.v1.trips import get_trip_endpoint

    trip_id = await _seed_trip_with_poi(session_factory)
    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        owner_id = str(trip.owner_user_id)
        trip.title = "유지 함수가 커밋하면 안 되는 변경"
        if flushed:
            await db.flush()
        with db.no_autoflush:
            response = await get_trip_endpoint(
                trip_id=trip_id,
                current_user_id=owner_id,
                db=db,
                kor_travel_map_client=None,
                weather_client=None,
            )
        assert response.data.trip.title == "유지 함수가 커밋하면 안 되는 변경"
        assert db.in_transaction()
        async with session_factory() as observer:
            assert (
                await observer.scalar(select(Trip.title).where(Trip.trip_id == trip_id))
                == "일출 여행"
            )
            assert (
                list(
                    await observer.scalars(
                        select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id)
                    )
                )
                == []
            )
        await db.rollback()


async def test_unchanged_input_preserves_etl_success_and_null_transitions_mark_stale(
    session_factory: Any,
) -> None:
    trip_id = await _seed_trip_with_poi(session_factory)
    await sync_trip_day_rise_sets(trip_id=trip_id)
    fetched = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
        assert row is not None
        row.status = "success"
        row.sunrise_at = fetched
        row.sunset_at = fetched
        row.moonrise_at = fetched
        row.moonset_at = fetched
        row.fetched_at = fetched
        row.raw_payload = {"fixture": "preserve"}
        row.stale = False
        await db.commit()
        await db.refresh(row)
        updated = row.updated_at
    await sync_trip_day_rise_sets(trip_id=trip_id)
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
        assert row is not None
        assert (
            row.status,
            row.stale,
            row.sunrise_at,
            row.sunset_at,
            row.moonrise_at,
            row.moonset_at,
            row.fetched_at,
            row.raw_payload,
            row.updated_at,
        ) == (
            "success",
            False,
            fetched,
            fetched,
            fetched,
            fetched,
            fetched,
            {"fixture": "preserve"},
            updated,
        )
        poi = await db.scalar(select(TripDayPoi).where(TripDayPoi.trip_id == trip_id))
        assert poi is not None
        poi.feature_snapshot = {"name": "좌표 없음"}
        await db.commit()
    await sync_trip_day_rise_sets(trip_id=trip_id)
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
        assert row is not None and row.stale and row.status == "pending_coord"
        assert row.longitude is None and row.latitude is None
        trip = await db.get(Trip, trip_id)
        assert trip is not None
        trip.start_date = None
        trip.end_date = None
        await db.commit()
    await sync_trip_day_rise_sets(trip_id=trip_id)
    async with session_factory() as db:
        row = await db.get(TripDayRiseSet, {"trip_id": trip_id, "day_index": 1})
        assert row is not None and row.stale and row.status == "pending_date"
        assert row.locdate is None


async def test_older_sync_cannot_overwrite_a_newer_poi_move(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    trip_id = await _seed_trip_with_poi(session_factory)
    owner, poi_id = await _trip_owner_and_poi(session_factory, trip_id)
    original_execute = AsyncSession.execute
    old_ready = asyncio.Event()
    release_old = asyncio.Event()
    first_session: int | None = None

    async def pause_old_sync(db: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal first_session
        if str(statement).startswith("INSERT INTO app.trip_day_rise_sets"):
            if first_session is None:
                first_session = id(db)
                old_ready.set()
                await asyncio.wait_for(release_old.wait(), timeout=10)
        return await original_execute(db, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", pause_old_sync)
    old = asyncio.create_task(sync_trip_day_rise_sets(trip_id=trip_id))
    move = None
    try:
        await asyncio.wait_for(old_ready.wait(), timeout=5)
        move = asyncio.create_task(
            client.patch(
                f"/trips/{trip_id}/pois/{poi_id}",
                cookies=auth_cookies(owner),
                headers={"If-Match": "1"},
                json={"day_index": 2},
            )
        )
        # 정정 전에는 이동+새 sync가 먼저 끝난다. Trip fence 도입 후에는 실제
        # PostgreSQL Lock wait를 확인한 다음 먼저 시작한 sync를 풀어준다.
        for _ in range(200):
            if move.done():
                break
            async with session_factory() as observer:
                blocked = await observer.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND query LIKE '%app.trips%FOR UPDATE%'"
                    )
                )
            if blocked:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("neither completed move nor database lock wait observed")
    finally:
        release_old.set()
        await old
        if move is not None:
            response = await asyncio.wait_for(move, timeout=5)
            assert response.status_code == 200, response.text
    async with session_factory() as db:
        rows = {
            row.day_index: row
            for row in await db.scalars(
                select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id)
            )
        }
    assert rows[1].status == "pending_coord" and rows[1].longitude is None
    assert rows[2].status == "pending_fetch"
    assert rows[2].longitude == 129.118
    assert str(rows[2].reference_poi_id) == poi_id


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
