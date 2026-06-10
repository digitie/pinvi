"""Telegram 즉시 알림 hook 통합 테스트 — T-106 (신규 trip / 동반자 초대)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

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
        self.sent.append(
            {
                "chat_id": chat_id,
                "message": message,
                "thread_id": thread_id,
                "parse_mode": parse_mode,
            }
        )
        return {"message_id": len(self.sent)}

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_telegram(monkeypatch: pytest.MonkeyPatch) -> _RecordingTelegram:
    """시스템 봇 토큰 설정 + notify의 client factory를 가짜로 교체."""
    from app.core.config import settings
    from app.services import telegram_notify

    fake = _RecordingTelegram()
    monkeypatch.setattr(settings, "tripmate_telegram_bot_token_default", "111:system_token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: fake)
    return fake


async def _seed_target(
    session_factory: Any, *, user_id: str, chat_id: str, is_default: bool = True
) -> uuid.UUID:
    from app.models.telegram_target import TelegramTarget

    async with session_factory() as db:
        target = TelegramTarget(
            user_id=uuid.UUID(user_id),
            telegram_chat_id=chat_id,
            is_default=is_default,
            last_verified_at=datetime.now(UTC),
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)
        return target.id


async def test_trip_create_notifies_owner_default_target(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    user_id, _ = verified_user
    await _seed_target(session_factory, user_id=user_id, chat_id="-100777")

    created = await client.post(
        "/trips",
        json={"title": "부산 2박 3일", "region_hint": "부산"},
        cookies=auth_cookies(user_id),
    )
    assert created.status_code == 201, created.text

    assert len(fake_telegram.sent) == 1
    sent = fake_telegram.sent[0]
    assert sent["chat_id"] == "-100777"
    assert "부산 2박 3일" in sent["message"]
    assert sent["parse_mode"] is None  # plain text


async def test_trip_create_without_target_is_silent_noop(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    user_id, _ = verified_user
    created = await client.post(
        "/trips", json={"title": "타겟 없음"}, cookies=auth_cookies(user_id)
    )
    assert created.status_code == 201
    assert fake_telegram.sent == []


async def test_send_failure_does_not_break_trip_create(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.models.telegram_target import TelegramTarget
    from app.services import telegram_notify

    user_id, _ = verified_user
    target_id = await _seed_target(session_factory, user_id=user_id, chat_id="-100888")

    failing = _RecordingTelegram(
        error=TelegramError("blocked", code="bot_forbidden", status_code=403)
    )
    monkeypatch.setattr(settings, "tripmate_telegram_bot_token_default", "111:system_token")
    monkeypatch.setattr(telegram_notify, "_make_client", lambda: failing)

    created = await client.post(
        "/trips", json={"title": "실패해도 생성"}, cookies=auth_cookies(user_id)
    )
    assert created.status_code == 201, created.text  # 알림 실패 비차단

    async with session_factory() as db:
        row = await db.get(TelegramTarget, target_id)
        assert row is not None
        assert row.last_send_status == "failed:bot_forbidden"
        assert row.is_enabled is False  # §5 — bot_forbidden은 target 비활성


async def test_companion_invite_notifies_existing_user(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
    fake_telegram: _RecordingTelegram,
) -> None:
    from app.models.user import User

    owner_id, _ = verified_user

    # 초대받을 기존 사용자 + default target.
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

    # owner는 target이 없으므로 초대받은 사용자 알림 1건만.
    assert len(fake_telegram.sent) == 1
    sent = fake_telegram.sent[0]
    assert sent["chat_id"] == "-100555"
    assert "서울 주말" in sent["message"]
    assert "지훈" in sent["message"]
    assert "@" not in sent["message"]  # 이메일 미포함
