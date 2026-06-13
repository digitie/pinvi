"""Telegram 알림 대상 CRUD + verify — `docs/integrations/telegram.md` §6. T-106.

bot token 원본은 저장하지 않는다(§1). 현 단계는 Pinvi 시스템 봇만 지원하며,
사용자는 봇을 자기 chat에 추가한 뒤 `telegram_chat_id`만 등록한다. `verify`는
시스템 봇 토큰으로 `getChat`을 호출해 chat 타입/제목 스냅샷을 채운다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram import TelegramClient, TelegramError
from app.models.telegram_target import TelegramTarget
from app.models.trip_telegram_target import TripTelegramTarget

SYSTEM_TOKEN_REF = "system"  # noqa: S105 - token이 아니라 ref 이름(설정 키)
MAX_TARGETS_PER_TRIP = 3


class TelegramTargetError(Exception):
    code = "TELEGRAM_ERROR"


class TelegramTargetNotFoundError(TelegramTargetError):
    code = "RESOURCE_NOT_FOUND"


class TripTargetLimitError(TelegramTargetError):
    """trip별 연결 한도(≤3) 초과."""

    code = "MAX_TARGETS_REACHED"


class TripTargetConflictError(TelegramTargetError):
    """이미 연결된 target."""

    code = "ALREADY_LINKED"


class TelegramTargetVerifyError(TelegramTargetError):
    """verify(getChat) 실패. `telegram_code`는 client §5 분류, `status_code`는 응답용."""

    def __init__(
        self,
        message: str,
        *,
        telegram_code: str,
        status_code: int,
        retry_after: int | None = None,
    ) -> None:
        self.telegram_code = telegram_code
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


_STATUS_BY_CODE: dict[str, int] = {
    "missing_chat_id": 422,
    "invalid_chat": 422,
    "invalid_topic": 422,
    "bot_forbidden": 403,
    "rate_limited": 429,
    "network_error": 503,
    "unknown_error": 502,
}


def _verify_error(exc: TelegramError) -> TelegramTargetVerifyError:
    status_code = _STATUS_BY_CODE.get(exc.code, 502)
    return TelegramTargetVerifyError(
        f"telegram verify 실패: {exc.code}",
        telegram_code=exc.code,
        status_code=status_code,
        retry_after=exc.retry_after,
    )


async def list_targets(db: AsyncSession, *, user_id: uuid.UUID) -> Sequence[TelegramTarget]:
    rows = await db.execute(
        select(TelegramTarget)
        .where(TelegramTarget.user_id == user_id, TelegramTarget.deleted_at.is_(None))
        .order_by(TelegramTarget.is_default.desc(), TelegramTarget.created_at.desc())
    )
    return rows.scalars().all()


async def get_target(
    db: AsyncSession, *, target_id: uuid.UUID, user_id: uuid.UUID
) -> TelegramTarget:
    row = await db.scalar(
        select(TelegramTarget).where(
            TelegramTarget.id == target_id,
            TelegramTarget.user_id == user_id,
            TelegramTarget.deleted_at.is_(None),
        )
    )
    if row is None:
        raise TelegramTargetNotFoundError("telegram target을 찾을 수 없습니다.")
    return row


async def _clear_default(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await db.execute(
        update(TelegramTarget)
        .where(
            TelegramTarget.user_id == user_id,
            TelegramTarget.deleted_at.is_(None),
            TelegramTarget.is_default.is_(True),
        )
        .values(is_default=False)
    )


async def _apply_verify(
    target: TelegramTarget,
    *,
    bot_token: str | None,
    client: TelegramClient | None,
) -> None:
    """시스템 봇 토큰이 설정돼 있으면 getChat으로 스냅샷을 채운다. 실패는 raise."""
    if not bot_token or client is None:
        return  # dev/미설정: 미검증 상태로 둔다.
    try:
        info = await client.verify_target(bot_token, target.telegram_chat_id)
    except TelegramError as exc:
        raise _verify_error(exc) from exc
    target.telegram_chat_type = info.get("telegram_chat_type")
    target.title_snapshot = info.get("title_snapshot")
    target.last_verified_at = datetime.now(UTC)
    target.last_send_status = "ok"
    target.is_enabled = True


async def create_target(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    telegram_chat_id: str,
    telegram_label: str | None,
    telegram_message_thread_id: str | None,
    is_default: bool,
    bot_token: str | None,
    client: TelegramClient | None,
) -> TelegramTarget:
    if is_default:
        await _clear_default(db, user_id=user_id)
    target = TelegramTarget(
        user_id=user_id,
        telegram_bot_token_ref=SYSTEM_TOKEN_REF,
        telegram_chat_id=telegram_chat_id,
        telegram_label=telegram_label,
        telegram_message_thread_id=telegram_message_thread_id,
        is_default=is_default,
    )
    # 등록 시 verify(§6.1) — 실패하면 persist하지 않는다.
    await _apply_verify(target, bot_token=bot_token, client=client)
    db.add(target)
    await db.flush()
    return target


async def verify_existing(
    db: AsyncSession,
    *,
    target_id: uuid.UUID,
    user_id: uuid.UUID,
    bot_token: str | None,
    client: TelegramClient | None,
) -> TelegramTarget:
    target = await get_target(db, target_id=target_id, user_id=user_id)
    try:
        await _apply_verify(target, bot_token=bot_token, client=client)
    except TelegramTargetVerifyError as exc:
        # 재검증 실패는 기록만 하고(§5 bot_forbidden→is_enabled=false) raise.
        target.last_send_status = f"failed:{exc.telegram_code}"
        if exc.telegram_code == "bot_forbidden":
            target.is_enabled = False
        await db.flush()
        raise
    await db.flush()
    return target


async def delete_target(db: AsyncSession, *, target_id: uuid.UUID, user_id: uuid.UUID) -> None:
    target = await get_target(db, target_id=target_id, user_id=user_id)
    target.deleted_at = datetime.now(UTC)
    target.is_enabled = False
    await db.flush()


# --- trip ↔ target 연결 (§6.5/6.6) -----------------------------------------


async def list_trip_targets(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> Sequence[TelegramTarget]:
    """trip에 연결된(소유자의 살아있는) target 목록."""
    rows = await db.execute(
        select(TelegramTarget)
        .join(TripTelegramTarget, TripTelegramTarget.telegram_target_id == TelegramTarget.id)
        .where(
            TripTelegramTarget.trip_id == trip_id,
            TelegramTarget.user_id == user_id,
            TelegramTarget.deleted_at.is_(None),
        )
        .order_by(TripTelegramTarget.created_at)
    )
    return rows.scalars().all()


async def link_trip_target(
    db: AsyncSession, *, trip_id: uuid.UUID, target_id: uuid.UUID, user_id: uuid.UUID
) -> TelegramTarget:
    """trip에 user 소유 target을 연결한다(≤3, 중복 금지). target 미존재 시 404."""
    target = await get_target(db, target_id=target_id, user_id=user_id)

    existing = await db.scalar(
        select(TripTelegramTarget).where(
            TripTelegramTarget.trip_id == trip_id,
            TripTelegramTarget.telegram_target_id == target_id,
        )
    )
    if existing is not None:
        raise TripTargetConflictError("이미 연결된 대상입니다.")

    count = await db.scalar(
        select(func.count())
        .select_from(TripTelegramTarget)
        .where(TripTelegramTarget.trip_id == trip_id)
    )
    if (count or 0) >= MAX_TARGETS_PER_TRIP:
        raise TripTargetLimitError("여행당 최대 3개 대상까지 연결할 수 있습니다.")

    db.add(TripTelegramTarget(trip_id=trip_id, telegram_target_id=target_id))
    await db.flush()
    return target


async def unlink_trip_target(db: AsyncSession, *, trip_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """trip↔target 연결을 해제한다(연결 row 없으면 404). target 자체는 삭제하지 않음."""
    link = await db.scalar(
        select(TripTelegramTarget).where(
            TripTelegramTarget.trip_id == trip_id,
            TripTelegramTarget.telegram_target_id == target_id,
        )
    )
    if link is None:
        raise TelegramTargetNotFoundError("연결을 찾을 수 없습니다.")
    await db.delete(link)
    await db.flush()
