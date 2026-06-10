"""Telegram 알림 outbox 통합 테스트 — T-106 §8 (enqueue hook + drain worker)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.telegram import TelegramError

pytestmark = pytest.mark.asyncio


class _RecordingTelegram:
    """send_to_target 호출을 기록하는 가짜 client."""

    def __init__(self, *, error: TelegramError | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._error = error

    async def send_to_target(
        self,
        token: str,
        chat_id: str,
        message: str,
        *,
        thread_id: str | None = None,
        parse_mode: str | None = "MarkdownV2",
    ) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        self.sent.append({"chat_id": chat_id, "message": message, "parse_mode": parse_mode})
        return {"message_id": len(self.sent)}

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_telegram(monkeypatch: pytest.MonkeyPatch) -> _RecordingTelegram:
    from app.core.config import settings
    from app.services import telegram_notify

    fake = _RecordingTelegram()
    monkeypatch.setattr(settings, "tripmate_telegram_bot_token_default", "111:system_token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: fake)
    return fake


async def _seed_target(session_factory: Any, *, user_id: str, chat_id: str) -> uuid.UUID:
    from app.models.telegram_target import TelegramTarget

    async with session_factory() as db:
        target = TelegramTarget(
            user_id=uuid.UUID(user_id),
            telegram_chat_id=chat_id,
            is_default=True,
            last_verified_at=datetime.now(UTC),
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)
        return target.id


async def _outbox_rows(session_factory: Any) -> list[Any]:
    from app.models.telegram_outbox import TelegramNotificationOutbox

    async with session_factory() as db:
        rows = await db.execute(
            select(TelegramNotificationOutbox).order_by(TelegramNotificationOutbox.created_at)
        )
        return list(rows.scalars())


async def test_trip_create_enqueues_then_worker_sends(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    from app.services.telegram_outbox import process_pending_telegram_batch

    user_id, _ = verified_user
    await _seed_target(session_factory, user_id=user_id, chat_id="-100777")

    created = await client.post(
        "/trips",
        json={"title": "부산 2박 3일", "region_hint": "부산"},
        cookies=auth_cookies(user_id),
    )
    assert created.status_code == 201, created.text

    # hook은 전송하지 않고 outbox에 적재만.
    rows = await _outbox_rows(session_factory)
    assert len(rows) == 1
    assert rows[0].category == "trip_created"
    assert rows[0].status == "pending"
    assert fake_telegram.sent == []

    # worker drain → 전송 + sent 마킹.
    async with session_factory() as db:
        result = await process_pending_telegram_batch(db)
    assert (result.claimed, result.sent) == (1, 1)
    assert len(fake_telegram.sent) == 1
    assert fake_telegram.sent[0]["chat_id"] == "-100777"
    assert "부산 2박 3일" in fake_telegram.sent[0]["message"]
    assert fake_telegram.sent[0]["parse_mode"] is None

    rows = await _outbox_rows(session_factory)
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None


async def test_companion_invite_enqueues_for_existing_user(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    from app.models.user import User
    from app.services.telegram_outbox import process_pending_telegram_batch

    owner_id, _ = verified_user
    async with session_factory() as db:
        invitee = User(
            email="friend@example.com",
            password_hash="x",
            nickname="친구",
            status="active",
            roles=["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(invitee)
        await db.commit()
        await db.refresh(invitee)
        invitee_id = str(invitee.user_id)
    await _seed_target(session_factory, user_id=invitee_id, chat_id="-100555")

    cookies = auth_cookies(owner_id)
    created = await client.post("/trips", json={"title": "서울 주말"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]

    invited = await client.post(
        f"/trips/{trip_id}/members",
        json={"email": "friend@example.com", "display_name": "지훈"},
        cookies=cookies,
    )
    assert invited.status_code == 201, invited.text

    rows = await _outbox_rows(session_factory)
    categories = {row.category for row in rows}
    assert categories == {"trip_created", "companion_invited"}

    async with session_factory() as db:
        result = await process_pending_telegram_batch(db)
    # owner는 target 없음 → trip_created는 skipped, 초대 알림만 전송.
    assert (result.sent, result.skipped) == (1, 1)
    assert len(fake_telegram.sent) == 1
    sent = fake_telegram.sent[0]
    assert sent["chat_id"] == "-100555"
    assert "서울 주말" in sent["message"]
    assert "@" not in sent["message"]


async def test_send_failure_schedules_retry_with_backoff(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.services import telegram_notify
    from app.services.telegram_outbox import process_pending_telegram_batch

    user_id, _ = verified_user
    await _seed_target(session_factory, user_id=user_id, chat_id="-100888")

    failing = _RecordingTelegram(error=TelegramError("429", code="rate_limited", status_code=429))
    monkeypatch.setattr(settings, "tripmate_telegram_bot_token_default", "111:system_token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: failing)

    created = await client.post(
        "/trips", json={"title": "재시도 여행"}, cookies=auth_cookies(user_id)
    )
    assert created.status_code == 201

    now = datetime.now(UTC)
    async with session_factory() as db:
        result = await process_pending_telegram_batch(db, now=now)
    assert (result.retried, result.failed) == (1, 0)

    rows = await _outbox_rows(session_factory)
    assert rows[0].status == "pending"  # 재시도 대기
    assert rows[0].attempts == 1
    assert rows[0].scheduled_at > now  # backoff로 미래 재예약


async def test_retry_exhaustion_marks_failed(
    session_factory: Any,
    verified_user: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.models.telegram_outbox import TelegramNotificationOutbox
    from app.services import telegram_notify
    from app.services.telegram_outbox import (
        MAX_TELEGRAM_ATTEMPTS,
        process_pending_telegram_batch,
    )

    user_id, _ = verified_user
    await _seed_target(session_factory, user_id=user_id, chat_id="-100999")

    failing = _RecordingTelegram(error=TelegramError("500", code="network_error", status_code=500))
    monkeypatch.setattr(settings, "tripmate_telegram_bot_token_default", "111:system_token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: failing)

    # 소진 직전 상태의 row를 직접 적재.
    async with session_factory() as db:
        db.add(
            TelegramNotificationOutbox(
                category="trip_created",
                payload={"user_id": user_id, "text": "마지막 시도"},
                status="pending",
                attempts=MAX_TELEGRAM_ATTEMPTS - 1,
                scheduled_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await process_pending_telegram_batch(db)
    assert result.failed == 1

    rows = await _outbox_rows(session_factory)
    assert rows[0].status == "failed"
    assert rows[0].attempts == MAX_TELEGRAM_ATTEMPTS


async def test_no_target_is_skipped_terminal(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    from app.services.telegram_outbox import process_pending_telegram_batch

    user_id, _ = verified_user
    created = await client.post(
        "/trips", json={"title": "타겟 없음"}, cookies=auth_cookies(user_id)
    )
    assert created.status_code == 201

    async with session_factory() as db:
        result = await process_pending_telegram_batch(db)
    assert (result.skipped, result.sent) == (1, 0)
    rows = await _outbox_rows(session_factory)
    assert rows[0].status == "skipped"  # 재시도하지 않는다.
    assert fake_telegram.sent == []
