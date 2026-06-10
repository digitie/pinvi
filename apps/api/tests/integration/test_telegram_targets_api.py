"""Telegram 알림 대상 API 통합 테스트 — T-106."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from app.api.v1.telegram_targets import get_telegram_client
from app.clients.telegram import TelegramError

pytestmark = pytest.mark.asyncio


class _FakeTelegram:
    """verify_target만 흉내내는 가짜 client (실 Telegram 호출 없음)."""

    def __init__(
        self, *, result: dict[str, Any] | None = None, error: TelegramError | None = None
    ) -> None:
        self._result = result or {"telegram_chat_type": "group", "title_snapshot": "가족 단톡"}
        self._error = error

    async def verify_target(self, token: str, chat_id: str) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        return self._result

    async def aclose(self) -> None:  # pragma: no cover - dependency 정리 인터페이스
        return None


def _override(fake: _FakeTelegram) -> Iterator[None]:
    from app.main import app

    app.dependency_overrides[get_telegram_client] = lambda: fake
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_telegram_client, None)


@pytest.fixture
def _with_system_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "tripmate_telegram_bot_token_default", "111:AAAA_system_token_value"
    )


async def test_create_verifies_then_lists_and_deletes(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    _with_system_bot: None,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    gen = _override(_FakeTelegram())
    next(gen)
    try:
        created = await client.post(
            "/users/me/telegram-targets",
            json={"telegram_chat_id": "-100999", "telegram_label": "가족", "is_default": True},
            cookies=cookies,
        )
        assert created.status_code == 201, created.text
        body = created.json()["data"]
        assert body["telegram_chat_id"] == "-100999"
        assert body["telegram_chat_type"] == "group"  # verify로 채워짐
        assert body["title_snapshot"] == "가족 단톡"
        assert body["last_send_status"] == "ok"
        target_id = body["id"]

        listed = await client.get("/users/me/telegram-targets", cookies=cookies)
        assert listed.status_code == 200
        assert [t["id"] for t in listed.json()["data"]] == [target_id]

        deleted = await client.delete(f"/users/me/telegram-targets/{target_id}", cookies=cookies)
        assert deleted.status_code == 204

        after = await client.get("/users/me/telegram-targets", cookies=cookies)
        assert after.json()["data"] == []
    finally:
        next(gen, None)


async def test_create_with_bot_forbidden_returns_403_and_persists_nothing(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    _with_system_bot: None,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    error = TelegramError("blocked", code="bot_forbidden", status_code=403)
    gen = _override(_FakeTelegram(error=error))
    next(gen)
    try:
        created = await client.post(
            "/users/me/telegram-targets",
            json={"telegram_chat_id": "-100777"},
            cookies=cookies,
        )
        assert created.status_code == 403, created.text
        assert created.json()["error"]["code"] == "bot_forbidden"

        listed = await client.get("/users/me/telegram-targets", cookies=cookies)
        assert listed.json()["data"] == []  # rollback — 미저장
    finally:
        next(gen, None)


async def test_create_without_system_bot_is_unverified(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    # 시스템 봇 토큰 미설정(dev) — verify 스킵, 미검증 상태로 생성.
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    gen = _override(_FakeTelegram())
    next(gen)
    try:
        created = await client.post(
            "/users/me/telegram-targets",
            json={"telegram_chat_id": "42"},
            cookies=cookies,
        )
        assert created.status_code == 201, created.text
        body = created.json()["data"]
        assert body["telegram_chat_type"] is None
        assert body["last_verified_at"] is None
    finally:
        next(gen, None)


async def test_verify_endpoint_updates_snapshot(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    _with_system_bot: None,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    gen = _override(
        _FakeTelegram(result={"telegram_chat_type": "supergroup", "title_snapshot": "여행방"})
    )
    next(gen)
    try:
        created = await client.post(
            "/users/me/telegram-targets",
            json={"telegram_chat_id": "-100123"},
            cookies=cookies,
        )
        target_id = created.json()["data"]["id"]

        verified = await client.post(
            f"/users/me/telegram-targets/{target_id}/verify",
            cookies=cookies,
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["data"]["telegram_chat_type"] == "supergroup"
    finally:
        next(gen, None)


async def test_delete_unknown_target_returns_404(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    missing = await client.delete(
        "/users/me/telegram-targets/00000000-0000-4000-8000-000000000000",
        cookies=cookies,
    )
    assert missing.status_code == 404
