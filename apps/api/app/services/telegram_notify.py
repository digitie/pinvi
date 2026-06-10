"""Telegram 즉시 알림 전송 — T-106 (신규 trip / 동반자 초대).

FastAPI `BackgroundTasks`에서 응답 후 실행된다. request 세션은 이미 닫혔으므로
`app.db.session.async_session_factory`(모듈 속성 — 테스트가 패치)를 통해 자체 세션을
연다. 알림 실패는 본 흐름을 깨지 않는다 — 로그 + `last_send_status` 기록만 한다.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.clients.telegram import TelegramClient, TelegramError
from app.core.config import settings
from app.models.telegram_target import TelegramTarget

logger = logging.getLogger(__name__)


def _make_client() -> TelegramClient:
    """실 전송용 client. 테스트는 이 함수를 monkeypatch한다."""
    http = httpx.AsyncClient(base_url=settings.tripmate_telegram_api_base)
    return TelegramClient(http, timeout_seconds=settings.tripmate_telegram_timeout_seconds)


async def send_user_notification(user_id: uuid.UUID, text: str) -> None:
    """user의 default(없으면 최신 enabled) target으로 plain text 알림을 보낸다.

    시스템 봇 미설정 / target 없음 → 조용히 no-op. 전송 실패 → 로그 + 상태 기록.
    절대 raise하지 않는다(BackgroundTasks용).
    """
    token = settings.tripmate_telegram_bot_token_default
    if not token:
        return

    # request 세션과 분리된 자체 세션 — 모듈 속성으로 동적 참조(테스트 패치 호환).
    from sqlalchemy import select

    from app.db import session as db_session

    try:
        async with db_session.async_session_factory() as db:
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
                return

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
            finally:
                await client.aclose()
            await db.commit()
    except Exception:
        logger.exception("telegram notify 처리 중 오류 user_id=%s", user_id)
