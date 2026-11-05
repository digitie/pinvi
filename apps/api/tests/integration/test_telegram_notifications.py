"""실제 마이그레이션·HTTP·DB 큐 경계. 외부 Telegram 호출은 소유 fixture다."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
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
        self.block: asyncio.Event | None = None
        self.started = asyncio.Event()

    async def send_to_target(
        self, token: str, chat_id: str, message: str, **kwargs: Any
    ) -> dict[str, int]:
        assert kwargs["parse_mode"] is None
        self.started.set()
        if self.block is not None:
            await self.block.wait()
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
    provider.error = TelegramError(
        "429 token=111:owned-test-token target=-100636", code="rate_limited", retry_after=3600
    )
    async with session_factory() as db:
        await process_one(db, now=now + timedelta(seconds=4))
    status = await delivery(session_factory)
    assert status.next_chunk == 1 and status.status == "pending"
    assert status.scheduled_at >= now + timedelta(seconds=3604)
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
