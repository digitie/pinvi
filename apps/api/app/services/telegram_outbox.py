"""Telegram 알림 outbox + 재시도 worker — `docs/integrations/telegram.md` §8. T-106.

email_queue와 같은 패턴: enqueue는 요청 트랜잭션에서 row만 넣고, lifespan drain
worker가 `FOR UPDATE SKIP LOCKED`로 claim해 전송한다. 실패는 exponential backoff로
재시도, 소진 시 `failed`. 대상/토큰이 없으면 `skipped`(재시도 무의미).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram import TelegramError
from app.core.config import settings
from app.models.telegram_outbox import TelegramNotificationOutbox
from app.services.telegram_notify import deliver_user_notification

logger = logging.getLogger(__name__)

MAX_TELEGRAM_ATTEMPTS = 5
# email_queue와 동일한 backoff 계열 (30s/5m/30m/1h/4h).
_RETRY_DELAYS_SECONDS = (30, 300, 1800, 3600, 14400)


def _retry_delay(attempts: int) -> int:
    index = min(attempts, len(_RETRY_DELAYS_SECONDS)) - 1
    return _RETRY_DELAYS_SECONDS[max(0, index)]


@dataclass(frozen=True)
class TelegramBatchResult:
    claimed: int
    sent: int
    skipped: int
    retried: int
    failed: int


async def enqueue_user_notification(
    db: AsyncSession,
    *,
    category: str,
    user_id: uuid.UUID,
    text: str,
) -> TelegramNotificationOutbox:
    """사용자 알림을 outbox에 적재한다(전송은 worker). commit은 호출자."""
    row = TelegramNotificationOutbox(
        category=category,
        payload={"user_id": str(user_id), "text": text},
        status="pending",
        scheduled_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


async def process_pending_telegram_batch(
    db: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> TelegramBatchResult:
    """pending 알림을 `FOR UPDATE SKIP LOCKED`로 claim해 한 batch 전송한다."""
    current = now or datetime.now(UTC)
    result = await db.execute(
        select(TelegramNotificationOutbox)
        .where(
            TelegramNotificationOutbox.status == "pending",
            TelegramNotificationOutbox.scheduled_at <= current,
        )
        .order_by(TelegramNotificationOutbox.scheduled_at, TelegramNotificationOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars())
    sent = skipped = retried = failed = 0

    for row in rows:
        row.attempts += 1
        try:
            user_id = uuid.UUID(str(row.payload.get("user_id")))
            text = str(row.payload.get("text") or "")
            outcome = await deliver_user_notification(db, user_id=user_id, text=text)
        except TelegramError as exc:
            if row.attempts >= MAX_TELEGRAM_ATTEMPTS:
                row.status = "failed"
                failed += 1
            else:
                row.scheduled_at = current + timedelta(seconds=_retry_delay(row.attempts))
                retried += 1
            row.last_error = str(exc)
            logger.warning(
                "telegram outbox 전송 실패 id=%s category=%s attempts=%s code=%s",
                row.id,
                row.category,
                row.attempts,
                exc.code,
            )
            continue
        except Exception as exc:  # payload 손상 등 — 재시도 무의미.
            row.status = "failed"
            row.last_error = str(exc)
            failed += 1
            logger.exception("telegram outbox 처리 오류 id=%s", row.id)
            continue

        if outcome == "skipped":
            row.status = "skipped"
            row.last_error = None
            skipped += 1
        else:
            row.status = "sent"
            row.sent_at = current
            row.last_error = None
            sent += 1

    if rows:
        await db.commit()
    return TelegramBatchResult(
        claimed=len(rows), sent=sent, skipped=skipped, retried=retried, failed=failed
    )


async def _drain_loop(interval: float, batch_size: int) -> None:
    from app.db import session as db_session

    while True:
        try:
            async with db_session.async_session_factory() as session:
                result = await process_pending_telegram_batch(session, limit=batch_size)
            # 배치가 가득이면 즉시 한 번 더, 아니면 interval 대기.
            if result.claimed < batch_size:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("telegram outbox drain 실패", exc_info=True)
            await asyncio.sleep(interval)


@asynccontextmanager
async def telegram_outbox_worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — telegram outbox drain worker(단일 task) 시작/정리."""
    if not settings.tripmate_telegram_outbox_worker_enabled:
        yield
        return
    task = asyncio.create_task(
        _drain_loop(
            settings.tripmate_telegram_outbox_drain_interval_seconds,
            settings.tripmate_telegram_outbox_batch_size,
        ),
        name="telegram-outbox-drain",
    )
    app.state.telegram_outbox_worker = task
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.telegram_outbox_worker = None
