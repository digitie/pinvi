"""Telegram 사용자 알림 delivery 코어 — T-106.

outbox worker(`telegram_outbox.process_pending_telegram_batch`)가 호출한다.
default(없으면 최신 enabled) target을 해석해 시스템 봇으로 plain text를 보낸다.
전송 실패는 `TelegramError`로 전파해 worker가 재시도를 분류한다(§8).
"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram import TelegramClient, TelegramError
from app.core.config import settings
from app.models.telegram_target import TelegramTarget

logger = logging.getLogger(__name__)


def _make_client() -> TelegramClient:
    """실 전송용 client. 테스트는 이 함수를 monkeypatch한다."""
    http = httpx.AsyncClient(base_url=settings.pinvi_telegram_api_base)
    return TelegramClient(http, timeout_seconds=settings.pinvi_telegram_timeout_seconds)


async def deliver_user_notification(db: AsyncSession, *, user_id: uuid.UUID, text: str) -> str:
    """user의 default target으로 알림을 보낸다.

    반환: `"sent"` | `"skipped"`(시스템 봇 미설정 또는 enabled target 없음 — 재시도 무의미).
    전송 실패는 `TelegramError` raise — 호출자(worker)가 재시도/소진을 판단한다.
    target의 `last_send_status`는 여기서 기록한다(commit은 호출자).
    """
    token = settings.pinvi_telegram_bot_token_default
    if not token:
        return "skipped"

    target = await db.scalar(
        select(TelegramTarget)
        .where(
            TelegramTarget.user_id == user_id,
            TelegramTarget.deleted_at.is_(None),
            TelegramTarget.is_enabled.is_(True),
        )
        .order_by(TelegramTarget.is_default.desc(), TelegramTarget.created_at.desc())
        .limit(1)
    )
    if target is None:
        return "skipped"

    client = _make_client()
    try:
        await client.send_to_target(
            token,
            target.telegram_chat_id,
            text,
            thread_id=target.telegram_message_thread_id,
            parse_mode=None,
        )
        target.last_send_status = "ok"
    except TelegramError as exc:
        target.last_send_status = f"failed:{exc.code}"
        if exc.code == "bot_forbidden":
            target.is_enabled = False
        logger.warning("telegram notify 실패 user_id=%s code=%s", user_id, exc.code)
        raise
    finally:
        await client.aclose()
    return "sent"
