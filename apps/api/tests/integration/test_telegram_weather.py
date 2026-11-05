"""실제 PG에서 특보의 opt-in·취소 역행·변경 fence·발송/오류 이력을 검증한다."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import event, select

from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.models.telegram_notification import (
    TelegramDelivery,
    TelegramPreferences,
)
from app.models.trip import Trip
from app.services.telegram_notifications import process_one
from app.services.telegram_planner import plan_due
from app.services.telegram_weather import plan_weather, prepare_weather
from tests.integration.test_telegram_notifications import Provider, setup_trip
from tests.integration.test_telegram_notifications import provider as provider

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
PREFERENCES = "/users/me/telegram-notification-preferences"


@pytest.fixture(autouse=True)
def delivery_clock() -> Iterator[None]:
    """주입한 worker 시계와 신규 delivery의 DB 예약 시각을 같은 기준에 둔다."""

    def set_initial_clock(_mapper: Any, _connection: Any, row: TelegramDelivery) -> None:
        if row.scheduled_at is None:
            row.scheduled_at = NOW

    event.listen(TelegramDelivery, "before_insert", set_initial_clock)
    try:
        yield
    finally:
        event.remove(TelegramDelivery, "before_insert", set_initial_clock)


class Weather:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now
        self.events: list[dict[str, Any]] = [self.event("issued")]
        self.calls = 0
        self.overrides: dict[str, Any] = {}
        self.http_status = 200

    def event(
        self, action: str, *, announcement: str = "official-1", event_id: str | None = None
    ) -> dict[str, Any]:
        stamp = (self.now - timedelta(minutes=1)).isoformat()
        return {
            "event_id": event_id or action,
            "announcement_id": announcement,
            "area_code": "official-area",
            "area_name": "부산",
            "warning_name": "호우",
            "stress_name": "경보",
            "action": action,
            "issued_at": stamp,
            "starts_at": stamp,
            "ends_at": None,
            "all_ends_at": None,
            "correlation_status": "unresolved",
            "scope_status": "verified",
            "first_seen_at": stamp,
            "bjd_prefixes": ["26"],
        }

    def request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        assert request.url.path == "/v1/weather/alert-events"
        data = {
            "namespace": "kr_bjd",
            "bjd_code": request.url.params["bjd_code"],
            "region_status": "known",
            "mapping_version": "owned-fixture",
            "mapping_valid_from": (self.now - timedelta(days=1)).isoformat(),
            "mapping_coverage": "partial",
            "unverified_scope_count": 23,
            "collection_status": "success",
            "last_attempt_at": self.now.isoformat(),
            "last_success_at": self.now.isoformat(),
            "last_error_code": None,
            "fresh": True,
            "events_complete": True,
            "retained_since": (self.now - timedelta(days=31)).isoformat(),
            "history_available_since": (self.now - timedelta(hours=2)).isoformat(),
            "queried_since": request.url.params["since"],
            "absence_is_clear": False,
            "events": self.events,
            **self.overrides,
        }
        return httpx.Response(self.http_status, json={"data": data, "secret": "must-not-leak"})

    def client(self) -> KorTravelWeatherClient:
        return KorTravelWeatherClient(
            httpx.AsyncClient(
                base_url="http://owned-weather.test", transport=httpx.MockTransport(self.request)
            ),
            max_attempts=1,
        )


async def setup(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    *,
    now: datetime = NOW,
) -> tuple[uuid.UUID, uuid.UUID, Any]:
    trip_id, _, cookies = await setup_trip(client, verified_user, auth_cookies, session_factory)
    assert (
        await client.put(
            PREFERENCES, json={"weather_enabled": True, "send_time": "23:59"}, cookies=cookies
        )
    ).status_code == 200
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        trip.primary_region_code, trip.primary_region_source = "26", "manual"
        pref = await db.get(TelegramPreferences, uuid.UUID(verified_user[0]))
        pref.weather_enabled_at = now - timedelta(hours=1)
        await db.commit()
    return uuid.UUID(trip_id), uuid.UUID(verified_user[0]), cookies


async def run(weather: Weather, *, now: datetime = NOW) -> dict[str, int]:
    source = weather.client()
    try:
        return await plan_due(now=now, weather_client=source)
    finally:
        await source.aclose()


async def test_weather_only_before_daily_time_dedupes_and_explicit_release(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
) -> None:
    trip_id, _, cookies = await setup(client, verified_user, auth_cookies, session_factory)
    weather = Weather()
    assert (await run(weather))["enqueued"] == 1
    assert (await run(weather))["enqueued"] == 0
    async with session_factory() as db:
        assert await process_one(db, now=NOW)
    assert len(provider.sent) == 1 and "발령 발표" in provider.sent[0]
    weather.events = []  # 정상 빈 응답에서 해제를 만들지 않는다.
    assert (await run(weather))["enqueued"] == 0
    weather.events = [weather.event("released", announcement="official-release")]
    assert (await run(weather))["enqueued"] == 1
    assert (await run(weather))["enqueued"] == 0
    async with session_factory() as db:
        assert await process_one(db, now=NOW)
    assert len(provider.sent) == 2 and "해제 발표" in provider.sent[1]
    assert all("일부 구역" in message and "공식 발표" in message for message in provider.sent)
    history = await client.get(
        "/users/me/telegram-notifications", cookies=cookies, params={"trip_id": str(trip_id)}
    )
    assert len(history.json()["data"]) == 2


async def test_cancelled_observation_invalidates_pending_and_stale_planner_cannot_reverse(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
) -> None:
    _, user_id, _ = await setup(client, verified_user, auth_cookies, session_factory)
    weather = Weather()
    source = weather.client()
    try:
        old = await prepare_weather(user_id, now=NOW, client=source)
        assert (await run(weather))["enqueued"] == 1
        weather.events = [weather.event("cancelled")]
        assert (await run(weather))["enqueued"] == 1
        async with session_factory() as db:
            assert (await plan_weather(db, user_id, old, now=NOW))[0] == 0
            await db.commit()
        async with session_factory() as db:
            assert await process_one(db, now=NOW)
        async with session_factory() as db:
            assert await process_one(db, now=NOW)
        assert len(provider.sent) == 1 and "발표 취소" in provider.sent[0]
        async with session_factory() as db:
            assert sorted((await db.scalars(select(TelegramDelivery.status))).all()) == [
                "sent",
                "skipped",
            ]
    finally:
        await source.aclose()


@pytest.mark.parametrize(
    "actions",
    [
        ["issued", "cancelled"],
        ["cancelled", "issued"],
        ["issued", "issued"],
    ],
)
async def test_same_first_seen_tie_never_resurrects_or_guesses_revision(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    actions: list[str],
) -> None:
    await setup(client, verified_user, auth_cookies, session_factory)
    weather = Weather()
    weather.events = [
        weather.event(action, event_id=f"observation-{i}") for i, action in enumerate(actions)
    ]
    result = await run(weather)
    if "cancelled" in actions:
        assert result["enqueued"] == 1
        async with session_factory() as db:
            await process_one(db, now=NOW)
        assert len(provider.sent) == 1 and "발표 취소" in provider.sent[0]
    else:
        assert result["enqueued"] == 0 and result["failed"] == 1
        assert provider.sent == []


@pytest.mark.parametrize(
    "failure", ["stale", "incomplete", "unknown_region", "transport", "wrong_region"]
)
async def test_safe_detailed_error_history_without_delivery_or_secret(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    failure: str,
) -> None:
    _, _, cookies = await setup(client, verified_user, auth_cookies, session_factory)
    weather = Weather()
    if failure == "transport":
        weather.http_status = 503
    elif failure == "stale":
        weather.overrides["fresh"] = False
    elif failure == "incomplete":
        weather.overrides["events_complete"] = False
    elif failure == "unknown_region":
        weather.overrides["region_status"] = "unknown"
    else:
        weather.events[0]["bjd_prefixes"] = ["11"]
    assert (await run(weather))["enqueued"] == 0
    assert (await run(weather))["enqueued"] == 0
    history = await client.get("/users/me/telegram-notifications", cookies=cookies)
    rows = history.json()["data"]
    assert len(rows) == 1 and rows[0]["error_code"].startswith("WEATHER_ALERT_")
    assert rows[0]["error_message"] and rows[0]["deliveries"] == []
    assert "must-not-leak" not in history.text and "owned-weather" not in history.text
    assert provider.sent == []


@pytest.mark.parametrize("change", ["region_aba", "consent", "expired", "version"])
async def test_current_policy_fences_before_send(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    change: str,
) -> None:
    trip_id, _user_id, cookies = await setup(client, verified_user, auth_cookies, session_factory)
    assert (await run(Weather()))["enqueued"] == 1
    if change == "consent":
        assert (
            await client.put(PREFERENCES, json={"weather_enabled": False}, cookies=cookies)
        ).status_code == 200
    if change in {"region_aba", "version"}:
        async with session_factory() as db:
            trip = await db.get(Trip, trip_id)
            trip.version += 2
            await db.commit()
    async with session_factory() as db:
        assert await process_one(
            db, now=NOW + timedelta(minutes=16) if change == "expired" else NOW
        )
    assert provider.sent == []
    async with session_factory() as db:
        assert await db.scalar(select(TelegramDelivery.status)) == "skipped"


async def test_old_put_preserves_weather_but_off_on_does_not_replay_old_announcement(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
) -> None:
    _, user_id, cookies = await setup(client, verified_user, auth_cookies, session_factory)
    response = await client.put(PREFERENCES, json={"daily_enabled": False}, cookies=cookies)
    assert response.json()["data"]["weather_enabled"] is True
    async with session_factory() as db:
        pref = await db.get(TelegramPreferences, user_id)
        pref.weather_enabled_at = NOW
        await db.commit()
    assert (await run(Weather()))["enqueued"] == 0


async def test_recent_weather_survives_midnight_within_same_trip(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
) -> None:
    before = datetime(2026, 11, 5, 14, 59, tzinfo=UTC)
    await setup(client, verified_user, auth_cookies, session_factory, now=before)
    assert (await run(Weather(before), now=before))["enqueued"] == 1
    async with session_factory() as db:
        assert await process_one(db, now=before + timedelta(minutes=2))
    assert len(provider.sent) == 1


@pytest.mark.parametrize("failure", ["stale", "incomplete"])
async def test_positive_cancellation_fence_survives_collection_failure(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    failure: str,
) -> None:
    await setup(client, verified_user, auth_cookies, session_factory)
    weather = Weather()
    assert (await run(weather))["enqueued"] == 1
    weather.events = [weather.event("cancelled")]
    weather.overrides["fresh" if failure == "stale" else "events_complete"] = False
    assert (await run(weather))["enqueued"] == 0
    async with session_factory() as db:
        assert await process_one(db, now=NOW)
    assert provider.sent == []
    async with session_factory() as db:
        assert await db.scalar(select(TelegramDelivery.status)) == "skipped"


@pytest.mark.parametrize("change", ["deleted", "disabled"])
async def test_invalid_weekly_destination_cannot_block_weather_optout(
    client: Any,
    verified_user: Any,
    auth_cookies: Any,
    session_factory: Any,
    provider: Provider,
    change: str,
) -> None:
    from app.models.telegram_target import TelegramTarget

    _, user_id, cookies = await setup(client, verified_user, auth_cookies, session_factory)
    async with session_factory() as db:
        weekly = TelegramTarget(user_id=user_id, telegram_chat_id="-10063799", last_verified_at=NOW)
        db.add(weekly)
        await db.commit()
        weekly_id = weekly.id
    body = {"weather_enabled": True, "weekly_enabled": True, "weekly_target_id": str(weekly_id)}
    assert (await client.put(PREFERENCES, json=body, cookies=cookies)).status_code == 200
    assert (await run(Weather()))["enqueued"] == 1
    async with session_factory() as db:
        weekly = await db.get(TelegramTarget, weekly_id)
        if change == "deleted":
            weekly.deleted_at = NOW
        else:
            weekly.is_enabled = False
        await db.commit()
    response = await client.put(
        PREFERENCES, json={**body, "weather_enabled": False}, cookies=cookies
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["weather_enabled"] is False
    async with session_factory() as db:
        assert await process_one(db, now=NOW)
    assert provider.sent == []
