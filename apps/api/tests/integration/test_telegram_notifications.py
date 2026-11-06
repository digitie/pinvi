"""실제 마이그레이션·HTTP·DB 큐 경계. 외부 Telegram 호출은 소유 fixture다."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.telegram import TelegramError
from app.models.telegram_notification import TelegramDelivery, TelegramNotification
from app.models.telegram_target import TelegramTarget
from app.models.trip_telegram_target import TripTelegramTarget
from app.services.telegram_notifications import process_one

pytestmark = pytest.mark.asyncio


class Provider:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.error: TelegramError | None = None
        self.delay = 0.0
        self.block: asyncio.Event | None = None
        self.started = asyncio.Event()

    async def send_to_target(
        self, token: str, chat_id: str, message: str, **kwargs: Any
    ) -> dict[str, int]:
        assert kwargs["parse_mode"] is None
        self.started.set()
        if self.block is not None:
            await self.block.wait()
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.sent.append(message)
        return {"message_id": len(self.sent)}

    async def aclose(self) -> None:
        pass


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Provider:
    from app.core.config import settings
    from app.services import telegram_notify

    fake = Provider()
    monkeypatch.setattr(settings, "pinvi_telegram_bot_token_default", "111:owned-test-token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: fake)
    return fake


@pytest.fixture
async def other_user(session_factory: Any) -> tuple[str, str]:
    from app.models.user import User

    async with session_factory() as db:
        row = User(
            email=f"telegram-other-{uuid.uuid4()}@pinvi.test",
            status="active",
            roles=["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(row)
        await db.commit()
        return str(row.user_id), row.email


async def setup_trip(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> tuple[str, str, Any]:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    response = await client.post(
        "/trips",
        json={"title": "부산 알림 검증", "start_date": "2026-11-05", "end_date": "2026-11-06"},
        cookies=cookies,
    )
    assert response.status_code == 201, response.text
    trip_id = response.json()["data"]["trip_id"]
    async with session_factory() as db:
        target = TelegramTarget(
            user_id=uuid.UUID(user_id),
            telegram_chat_id="-100636",
            last_verified_at=datetime.now(UTC),
        )
        db.add(target)
        await db.flush()
        db.add(TripTelegramTarget(trip_id=uuid.UUID(trip_id), telegram_target_id=target.id))
        await db.commit()
        return trip_id, str(target.id), cookies


async def send(client: Any, trip_id: str, cookies: Any, **body: Any) -> Any:
    return await client.post(
        f"/trips/{trip_id}/telegram/send",
        json={"request_id": str(uuid.uuid4()), "scope": "trip", **body},
        cookies=cookies,
    )


async def delivery(session_factory: Any) -> TelegramDelivery:
    async with session_factory() as db:
        value = await db.scalar(select(TelegramDelivery))
        assert value is not None
        return value


async def test_manual_idempotency_snapshot_and_scope(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    from app.models.trip import Trip

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    request_id = str(uuid.uuid4())
    first = await send(client, trip_id, cookies, request_id=request_id)
    assert first.status_code == 202, first.text
    assert provider.sent == []
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        trip.title = "변경된 제목"
        await db.commit()
    repeated = await send(client, trip_id, cookies, request_id=request_id)
    assert repeated.json()["data"]["id"] == first.json()["data"]["id"]
    mismatch = await send(client, trip_id, cookies, request_id=request_id, scope="day", day_index=1)
    assert mismatch.status_code == 422
    invalid = await send(client, trip_id, cookies, scope="day")
    assert invalid.status_code == 422
    missing = await send(client, trip_id, cookies, scope="day", day_index=999)
    assert missing.status_code == 404
    async with session_factory() as db:
        assert await process_one(db)
    assert len(provider.sent) == 1
    assert "부산 알림 검증" in provider.sent[0] and "변경된 제목" not in provider.sent[0]


@pytest.mark.parametrize(
    "change", ["unlink_relink", "reverify", "delete", "trip_delete", "owner_change"]
)
async def test_guard_rejects_changed_destination(
    client: Any,
    verified_user: Any,
    other_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    change: str,
) -> None:
    from app.models.trip import Trip

    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    response = await send(client, trip_id, cookies)
    assert response.status_code == 202
    async with session_factory() as db:
        if change == "unlink_relink":
            link = await db.get(TripTelegramTarget, (uuid.UUID(trip_id), uuid.UUID(target_id)))
            await db.delete(link)
            await db.flush()
            db.add(
                TripTelegramTarget(
                    trip_id=uuid.UUID(trip_id), telegram_target_id=uuid.UUID(target_id)
                )
            )
        elif change == "reverify":
            target = await db.get(TelegramTarget, uuid.UUID(target_id))
            target.generation = uuid.uuid4()
        elif change == "delete":
            target = await db.get(TelegramTarget, uuid.UUID(target_id))
            target.deleted_at = datetime.now(UTC)
        else:
            trip = await db.get(Trip, uuid.UUID(trip_id))
            if change == "trip_delete":
                trip.deleted_at = datetime.now(UTC)
            else:
                trip.owner_user_id = uuid.UUID(other_user[0])
        await db.commit()
    async with session_factory() as db:
        assert await process_one(db)
    assert provider.sent == []
    assert (await delivery(session_factory)).status == "skipped"


async def test_chunks_resume_and_retry_after_safe_ui_error(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (await send(client, trip_id, cookies)).status_code == 202
    async with session_factory() as db:
        row = await db.scalar(select(TelegramNotification))
        row.chunks = ["첫 chunk", "둘째 chunk"]
        await db.commit()
    now = datetime.now(UTC) + timedelta(seconds=1)
    async with session_factory() as db:
        await process_one(db, now=now)
    assert provider.sent == ["첫 chunk"]
    provider.delay = 0.05
    provider.error = TelegramError(
        "429 token=111:owned-test-token target=-100636", code="rate_limited", retry_after=3600
    )
    async with session_factory() as db:
        await process_one(db, now=now + timedelta(seconds=4))
    status = await delivery(session_factory)
    assert status.next_chunk == 1 and status.status == "pending"
    assert status.scheduled_at >= now + timedelta(seconds=3604.04)
    history = await client.get("/users/me/telegram-notifications", cookies=cookies)
    assert history.status_code == 200
    assert "rate_limited" in history.text and "재시도" in history.text
    assert "111:owned-test-token" not in history.text and "-100636" not in history.text
    provider.error = None
    async with session_factory() as db:
        assert not await process_one(db, now=now + timedelta(seconds=3603))
    async with session_factory() as db:
        await process_one(db, now=now + timedelta(seconds=3605))
    assert provider.sent == ["첫 chunk", "둘째 chunk"]
    assert (await delivery(session_factory)).status == "sent"


async def test_two_workers_do_not_claim_same_chunk(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    await send(client, trip_id, cookies)
    provider.block = asyncio.Event()

    async def worker() -> bool:
        async with session_factory() as db:
            return await process_one(db)

    running = asyncio.create_task(worker())
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    try:
        assert not await worker()
    finally:
        provider.block.set()
        await running
    assert len(provider.sent) == 1


async def test_cancelled_worker_releases_claim(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    await send(client, trip_id, cookies)
    provider.block = asyncio.Event()

    async def worker() -> bool:
        async with session_factory() as db:
            return await process_one(db)

    running = asyncio.create_task(worker())
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    provider.block = None
    assert await worker()
    assert len(provider.sent) == 1


async def test_owner_only_and_preferences_validation(
    client: Any, verified_user: Any, other_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    assert (await send(client, trip_id, auth_cookies(other_user[0]))).status_code == 403
    endpoint = "/users/me/telegram-notification-preferences"
    initial = await client.get(endpoint, cookies=cookies)
    assert initial.status_code == 200 and initial.json()["data"]["daily_enabled"] is False
    bad = await client.put(
        endpoint, json={"weekly_enabled": True, "send_time": "25:00"}, cookies=cookies
    )
    assert bad.status_code == 422
    alien = await client.put(
        endpoint,
        json={"weekly_enabled": True, "weekly_target_id": target_id},
        cookies=auth_cookies(other_user[0]),
    )
    assert alien.status_code == 422
    good = await client.put(
        endpoint,
        json={
            "daily_enabled": True,
            "weekly_enabled": True,
            "weekly_target_id": target_id,
            "send_time": "07:30",
        },
        cookies=cookies,
    )
    assert good.status_code == 200, good.text
    assert good.json()["data"]["send_time"] == "07:30"


async def test_enqueue_does_not_take_multiple_destination_locks(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    async with session_factory() as holder:
        locked_target = await holder.get(TelegramTarget, uuid.UUID(target_id))
        assert locked_target is not None
        locked_target.last_send_status = "failed:bot_forbidden"
        await holder.flush()  # legacy ORM UPDATE와 같은 NO KEY UPDATE 잠금
        try:
            response = await asyncio.wait_for(send(client, trip_id, cookies), timeout=1)
            assert response.status_code == 202, response.text
        finally:
            await holder.rollback()


async def test_kst_daily_weekly_dedup_and_consent_revocation(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    from app.models.kasi import TripDayRiseSet
    from app.services.telegram_planner import plan_due

    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    body = {
        "daily_enabled": True,
        "weekly_enabled": True,
        "weekly_target_id": target_id,
        "weekly_day": 3,
        "send_time": "08:00",
    }
    endpoint = "/users/me/telegram-notification-preferences"
    assert (await client.put(endpoint, json=body, cookies=cookies)).status_code == 200
    async with session_factory() as db:
        db.add(
            TripDayRiseSet(
                trip_id=uuid.UUID(trip_id),
                day_index=1,
                locdate=date(2026, 11, 5),
                sunrise_at=datetime(2026, 11, 4, 21, 30, tzinfo=UTC),
                status="success",
                stale=False,
            )
        )
        await db.commit()
    before = await plan_due(now=datetime(2026, 11, 4, 22, 59, tzinfo=UTC))
    assert before["enqueued"] == 0
    now = datetime(2026, 11, 4, 23, 0, tzinfo=UTC)  # 한국 11/5 목요일08:00
    first, second = await asyncio.gather(plan_due(now=now), plan_due(now=now))
    assert first["enqueued"] + second["enqueued"] == 3
    async with session_factory() as db:
        rows = list((await db.scalars(select(TelegramNotification))).all())
        assert len(rows) == 3
        daily = [row for row in rows if row.category == "daily_brief"]
        assert len(daily) == 2
        assert any("일출: 06:30" in "".join(row.chunks) for row in daily)
        assert all("날씨:" in "".join(row.chunks) for row in daily)
        assert all(
            "2026-11-05" in row.occurrence_key or "2026-11-06" in row.occurrence_key for row in rows
        )
    # 실제 변경 없는 저장은 기존 동의를 폐기하지 않는다.
    assert (await client.put(endpoint, json=body, cookies=cookies)).status_code == 200
    assert (
        await client.put(endpoint, json={"send_time": "08:00"}, cookies=cookies)
    ).status_code == 200
    async with session_factory() as db:
        while await process_one(db, now=datetime.now(UTC) + timedelta(hours=1)):
            pass
    assert provider.sent == []
    async with session_factory() as db:
        statuses = list((await db.scalars(select(TelegramDelivery.status))).all())
        assert statuses == ["skipped"] * 3
    # off→on으로 바뀌어도 같은 일간·주간 occurrence를 다시 만들지 않는다.
    await client.put(endpoint, json=body, cookies=cookies)
    assert (await plan_due(now=now))["enqueued"] == 0


async def test_planner_principal_is_separate_from_user_login(
    client: Any, verified_user: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "pinvi_telegram_planner_key", "owned-planner-test-key")
    cookies = auth_cookies(verified_user[0])
    assert (await client.post("/internal/telegram/plan", cookies=cookies)).status_code == 404
    assert (
        await client.post(
            "/internal/telegram/plan", headers={"X-Pinvi-Notification-Planner-Key": "wrong"}
        )
    ).status_code == 404
    good = await client.post(
        "/internal/telegram/plan",
        headers={"X-Pinvi-Notification-Planner-Key": "owned-planner-test-key"},
    )
    assert good.status_code == 200
    assert good.json()["data"]["enqueued"] == 0


async def test_restore_boundary_counts_new_pending_delivery(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.services.cache_target_final_boundary import _application_queue_counts

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (await send(client, trip_id, cookies)).status_code == 202
    async with session_factory() as db:
        _, telegram, _ = await _application_queue_counts(db)
        # 기존 trip_created1 + 신규 일정 대상1. pending 새 큐를 빼면 quiescence를 오판한다.
        assert telegram == 2


@pytest.mark.parametrize("invalid", ["deleted", "disabled"])
async def test_opt_out_succeeds_after_weekly_target_becomes_invalid(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    invalid: str,
) -> None:
    from app.services.telegram_planner import plan_due

    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    body = {"daily_enabled": True, "weekly_enabled": True, "weekly_target_id": target_id}
    endpoint = "/users/me/telegram-notification-preferences"
    assert (await client.put(endpoint, json=body, cookies=cookies)).status_code == 200
    async with session_factory() as db:
        target = await db.get(TelegramTarget, uuid.UUID(target_id))
        if invalid == "deleted":
            target.deleted_at = datetime.now(UTC)
        else:
            target.is_enabled = False
        valid = TelegramTarget(
            user_id=uuid.UUID(verified_user[0]),
            telegram_chat_id="-100638",
            last_verified_at=datetime.now(UTC),
        )
        db.add(valid)
        await db.flush()
        db.add(TripTelegramTarget(trip_id=uuid.UUID(trip_id), telegram_target_id=valid.id))
        await db.commit()
    assert (await plan_due(now=datetime(2026, 11, 5, 0, 0, tzinfo=UTC)))["enqueued"] == 2
    response = await client.put(
        endpoint, json={**body, "daily_enabled": False, "weekly_enabled": False}, cookies=cookies
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["daily_enabled"] is False
    async with session_factory() as db:
        while await process_one(db, now=datetime.now(UTC) + timedelta(hours=1)):
            pass
    assert provider.sent == []


async def test_opt_out_does_not_wait_for_weather_enrichment(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import telegram_planner

    _, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    endpoint = "/users/me/telegram-notification-preferences"
    assert (
        await client.put(endpoint, json={"daily_enabled": True}, cookies=cookies)
    ).status_code == 200
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_context(*args: Any, **kwargs: Any) -> str:
        started.set()
        await release.wait()
        return "날씨: 소유 지연 fixture"

    monkeypatch.setattr(telegram_planner, "daily_context", slow_context)
    planning = asyncio.create_task(
        telegram_planner.plan_due(now=datetime(2026, 11, 5, 0, 0, tzinfo=UTC))
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    try:
        response = await asyncio.wait_for(
            client.put(endpoint, json={"daily_enabled": False}, cookies=cookies), timeout=1
        )
        assert response.status_code == 200, response.text
    finally:
        release.set()
        await planning
    async with session_factory() as db:
        assert list((await db.scalars(select(TelegramNotification.id))).all()) == []


@pytest.mark.parametrize("change", ["trip_date", "day_delete", "midnight", "weekly_date"])
async def test_scheduled_delivery_rechecks_dates_and_kst_validity(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    change: str,
) -> None:
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.services.telegram_planner import plan_due

    trip_id, target_id, cookies = await setup_trip(
        client, verified_user, auth_cookies, session_factory
    )
    weekly = change == "weekly_date"
    body = {
        "daily_enabled": not weekly,
        "weekly_enabled": weekly,
        "weekly_target_id": target_id if weekly else None,
        "weekly_day": 3,
    }
    assert (
        await client.put("/users/me/telegram-notification-preferences", json=body, cookies=cookies)
    ).status_code == 200
    await plan_due(now=datetime(2026, 11, 5, 0, 0, tzinfo=UTC))
    async with session_factory() as db:
        for pending in (await db.scalars(select(TelegramDelivery))).all():
            pending.scheduled_at = datetime(2026, 11, 5, 0, tzinfo=UTC)
        if change in {"trip_date", "weekly_date"}:
            trip = await db.get(Trip, uuid.UUID(trip_id))
            trip.start_date, trip.end_date = date(2026, 12, 5), date(2026, 12, 6)
        elif change == "day_delete":
            day = await db.get(TripDay, (uuid.UUID(trip_id), 1))
            await db.delete(day)
            rows = list((await db.scalars(select(TelegramNotification))).all())
            for row in rows:
                if "2일차" in "".join(row.chunks):
                    recipient = await db.scalar(
                        select(TelegramDelivery).where(TelegramDelivery.notification_id == row.id)
                    )
                    recipient.scheduled_at = datetime(2026, 11, 7, 0, tzinfo=UTC)
        await db.commit()
    current = (
        datetime(2026, 11, 5, 15, 1, tzinfo=UTC)
        if change == "midnight"
        else datetime(2026, 11, 5, 1, tzinfo=UTC)
    )
    async with session_factory() as db:
        while await process_one(db, now=current):
            pass
    assert provider.sent == []
    async with session_factory() as db:
        processed = list(
            (
                await db.scalars(
                    select(TelegramDelivery).where(TelegramDelivery.status != "pending")
                )
            ).all()
        )
        assert processed
        assert all(
            row.error_code == ("schedule_expired" if change == "midnight" else "schedule_changed")
            for row in processed
        )


async def test_cached_daily_weather_works_with_one_database_connection(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.clients.kor_travel_weather import WeatherMarkerOut, WeatherValueOut
    from app.core.config import settings
    from app.db import session as db_session
    from app.models.poi import TripDayPoi
    from app.models.weather_location_link import WeatherLocationLink
    from app.services.telegram_planner import plan_due

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            "/users/me/telegram-notification-preferences",
            json={"daily_enabled": True},
            cookies=cookies,
        )
    ).status_code == 200
    async with session_factory() as db:
        db.add(
            TripDayPoi(
                trip_id=uuid.UUID(trip_id),
                day_index=1,
                sort_order="a0",
                feature_id="f_owned_weather",
                feature_snapshot={
                    "name": "소유 날씨 장소",
                    "coord": {"lon": 129.118, "lat": 35.153},
                },
                added_by_user_id=uuid.UUID(verified_user[0]),
            )
        )
        db.add(
            WeatherLocationLink(
                feature_id="f_owned_weather",
                location_id="owned-weather",
                source_location_ids=["owned-weather"],
                lat=35.153,
                lon=129.118,
                distance_km=0,
                resolved_at=datetime.now(UTC),
                stale=False,
            )
        )
        await db.commit()

    class CachedWeather:
        forecasts = 0

        async def resolve(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("공식 해석 캐시 적중이면 resolve 호출이 없어야 함")

        async def markers(self, *args: Any, **kwargs: Any) -> Any:
            return (WeatherMarkerOut(location_id="owned-weather"),)

        async def forecast(self, *args: Any, **kwargs: Any) -> Any:
            self.forecasts += 1
            return (
                WeatherValueOut(
                    value_id="owned-v1",
                    location_id="owned-weather",
                    provider="python-kma-api",
                    dataset_key="kma_short_forecast",
                    weather_domain="kma_short_forecast",
                    forecast_style="short",
                    metric_key="TMP",
                    metric_name="기온",
                    value_number=18,
                    unit="℃",
                    target_at=datetime(2026, 11, 5, 0, tzinfo=UTC),
                    normalization_version="v1",
                    collected_at=datetime.now(UTC),
                    source_record_key="owned-weather-source",
                ),
            )

    weather = CachedWeather()
    engine = create_async_engine(
        settings.pinvi_database_url, pool_size=1, max_overflow=0, pool_timeout=0.2
    )
    monkeypatch.setattr(
        db_session, "async_session_factory", async_sessionmaker(engine, expire_on_commit=False)
    )
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", False)
    try:
        result = await plan_due(now=datetime(2026, 11, 5, 0, tzinfo=UTC), weather_client=weather)
        assert result["enqueued"] == 2
        async with session_factory() as db:
            messages = list((await db.scalars(select(TelegramNotification.chunks))).all())
        assert weather.forecasts == 1
        assert any("기온" in "".join(chunks) and "18" in "".join(chunks) for chunks in messages)
    finally:
        await engine.dispose()


async def test_completed_admin_disable_fences_worker_waiting_on_trip(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    from sqlalchemy import event

    from app.db import session as db_session
    from app.models.trip import Trip
    from app.models.user import User

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (await send(client, trip_id, cookies)).status_code == 202
    async with session_factory() as db:
        admin = User(
            email=f"telegram-admin-{uuid.uuid4()}@pinvi.test",
            status="active",
            roles=["admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        admin_id = str(admin.user_id)
    reached = asyncio.Event()

    def waiting(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if "app.trips" in statement and "FOR UPDATE" in statement.upper():
            reached.set()

    async def worker() -> bool:
        async with session_factory() as db:
            return await process_one(db)

    async with session_factory() as holder:
        await holder.scalar(
            select(Trip).where(Trip.trip_id == uuid.UUID(trip_id)).with_for_update()
        )
        event.listen(db_session.engine.sync_engine, "before_cursor_execute", waiting)
        running = asyncio.create_task(worker())
        try:
            await asyncio.wait_for(reached.wait(), timeout=5)
            disabled = await client.post(
                f"/admin/users/{verified_user[0]}/disable",
                json={"access_reason": "소유 WSL 알림 계정 철회 경합"},
                cookies=auth_cookies(admin_id),
            )
            assert disabled.status_code == 200, disabled.text
            assert disabled.json()["data"]["is_active"] is False
        finally:
            await holder.rollback()
            await running
            event.remove(db_session.engine.sync_engine, "before_cursor_execute", waiting)
    assert provider.sent == []
    assert (await delivery(session_factory)).status == "skipped"


async def test_one_oversized_user_does_not_block_later_users_and_has_ui_error(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.models.poi import TripDayPoi
    from app.models.telegram_notification import TelegramPreferences
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.telegram_planner import plan_due

    _, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            "/users/me/telegram-notification-preferences",
            json={"daily_enabled": True},
            cookies=cookies,
        )
    ).status_code == 200
    poison_id, poison_trip = uuid.UUID(int=1), uuid.uuid4()
    async with session_factory() as db:
        db.add(
            User(
                user_id=poison_id,
                email="oversized-telegram@pinvi.test",
                status="active",
                roles=["user"],
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(
            Trip(
                trip_id=poison_trip,
                owner_user_id=poison_id,
                title="큰 일정",
                start_date=date(2026, 11, 5),
                end_date=date(2026, 11, 5),
            )
        )
        await db.flush()
        db.add(TripDay(trip_id=poison_trip, day_index=1))
        target = TelegramTarget(
            user_id=poison_id, telegram_chat_id="-1000001", last_verified_at=datetime.now(UTC)
        )
        db.add(target)
        await db.flush()
        db.add(TripTelegramTarget(trip_id=poison_trip, telegram_target_id=target.id))
        db.add(TelegramPreferences(user_id=poison_id, daily_enabled=True, send_time="08:00"))
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=poison_trip,
                    day_index=1,
                    sort_order=f"{index:05}",
                    feature_snapshot={"name": f"장소 {index}"},
                    user_note="긴메모" * 160,
                    added_by_user_id=poison_id,
                )
                for index in range(2000)
            ]
        )
        await db.commit()
    result = await plan_due(now=datetime(2026, 11, 5, 0, tzinfo=UTC))
    assert result["enqueued"] == 2 and result["failed"] == 1
    async with session_factory() as db:
        failure = await db.scalar(
            select(TelegramNotification).where(TelegramNotification.user_id == poison_id)
        )
        assert failure is not None and failure.error_code == "TELEGRAM_MESSAGE_TOO_LARGE"
    history = await client.get(
        "/users/me/telegram-notifications", cookies=auth_cookies(str(poison_id))
    )
    assert history.status_code == 200
    assert "일정이 너무 길" in history.text and "긴메모" not in history.text


async def test_unexpected_error_for_one_user_does_not_stop_later_users(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 사용자의 예상 밖 오류가 user_id 뒤 순서의 모든 예약을 매분 멈추지 않는다."""
    from app.models.telegram_notification import TelegramPreferences
    from app.models.user import User
    from app.services import telegram_planner

    _, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            "/users/me/telegram-notification-preferences",
            json={"daily_enabled": True},
            cookies=cookies,
        )
    ).status_code == 200
    poison_id = uuid.UUID(int=1)  # user_id 순으로 먼저 처리된다.
    async with session_factory() as db:
        db.add(
            User(
                user_id=poison_id,
                email="planner-poison@pinvi.test",
                status="active",
                roles=["user"],
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(TelegramPreferences(user_id=poison_id, daily_enabled=True, send_time="08:00"))
        await db.commit()
    original = telegram_planner.plan_user

    async def plan_user(db: Any, user_id: uuid.UUID, **kwargs: Any) -> int:
        if user_id == poison_id:
            raise RuntimeError("secret-bearing message must not be stored")
        return await original(db, user_id, **kwargs)

    monkeypatch.setattr(telegram_planner, "plan_user", plan_user)
    result = await telegram_planner.plan_due(now=datetime(2026, 11, 5, 0, tzinfo=UTC))
    assert result["enqueued"] == 2 and result["failed"] == 1
    async with session_factory() as db:
        assert (
            await db.scalar(
                select(TelegramNotification).where(TelegramNotification.user_id == poison_id)
            )
        ) is None


async def test_manual_send_backlog_is_capped_per_user(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    """한 사용자가 대기 전송을 무한히 쌓아 다른 사용자의 기한 있는 특보를 밀어내지 않는다."""
    from app.services.telegram_notifications import MANUAL_PENDING_LIMIT

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    first_id = str(uuid.uuid4())
    accepted = [await send(client, trip_id, cookies, request_id=first_id)]
    accepted += [await send(client, trip_id, cookies) for _ in range(MANUAL_PENDING_LIMIT - 1)]
    assert [r.status_code for r in accepted] == [202] * MANUAL_PENDING_LIMIT
    blocked = await send(client, trip_id, cookies)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["detail"]["code"] == "TELEGRAM_SEND_BACKLOG"
    # 같은 요청의 재시도는 상한과 무관하게 기존 응답을 돌려준다.
    retried = await send(client, trip_id, cookies, request_id=first_id)
    assert retried.status_code == 202
    assert retried.json()["data"]["id"] == accepted[0].json()["data"]["id"]
    async with session_factory() as db:
        assert await process_one(db)
    assert (await send(client, trip_id, cookies)).status_code == 202


async def test_expired_scheduled_retry_is_closed_before_future_retry_at(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any, provider: Provider
) -> None:
    from app.services.telegram_planner import plan_due

    _, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            "/users/me/telegram-notification-preferences",
            json={"daily_enabled": True},
            cookies=cookies,
        )
    ).status_code == 200
    before_midnight = datetime(2026, 11, 5, 14, 59, tzinfo=UTC)
    await plan_due(now=before_midnight)
    async with session_factory() as db:
        for pending in (await db.scalars(select(TelegramDelivery))).all():
            pending.scheduled_at = before_midnight
        await db.commit()
    provider.error = TelegramError("owned future retry", code="rate_limited", retry_after=3600)
    async with session_factory() as db:
        while await process_one(db, now=before_midnight):
            pass
    provider.error = None
    async with session_factory() as db:
        assert await process_one(db, now=datetime(2026, 11, 5, 15, 1, tzinfo=UTC))
        while await process_one(db, now=datetime(2026, 11, 5, 15, 1, tzinfo=UTC)):
            pass
    async with session_factory() as db:
        rows = list((await db.scalars(select(TelegramDelivery))).all())
        assert rows and all(
            row.status == "skipped" and row.error_code == "schedule_expired" for row in rows
        )
    assert provider.sent == []


async def test_scheduled_chunk_does_not_cross_midnight_while_waiting_on_policy_locks(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import event

    from app.db import session as db_session
    from app.models.trip import Trip
    from app.services import telegram_notifications
    from app.services.telegram_planner import plan_due

    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            "/users/me/telegram-notification-preferences",
            json={"daily_enabled": True},
            cookies=cookies,
        )
    ).status_code == 200
    now = datetime(2026, 11, 5, 14, 59, 55, tzinfo=UTC)
    await plan_due(now=now)
    async with session_factory() as db:
        for pending in (await db.scalars(select(TelegramDelivery))).all():
            pending.scheduled_at = now
        await db.commit()
    clock = {"elapsed": 0.0}
    monkeypatch.setattr(telegram_notifications, "monotonic", lambda: clock["elapsed"])
    reached = asyncio.Event()

    def waiting(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if "app.trips" in statement and "FOR UPDATE" in statement.upper():
            reached.set()

    async def worker() -> bool:
        async with session_factory() as db:
            return await process_one(db, now=now)

    async with session_factory() as holder:
        await holder.scalar(
            select(Trip).where(Trip.trip_id == uuid.UUID(trip_id)).with_for_update()
        )
        event.listen(db_session.engine.sync_engine, "before_cursor_execute", waiting)
        running = asyncio.create_task(worker())
        try:
            await asyncio.wait_for(reached.wait(), timeout=5)
            clock["elapsed"] = 10
        finally:
            await holder.rollback()
            await running
            event.remove(db_session.engine.sync_engine, "before_cursor_execute", waiting)
    assert provider.sent == []
