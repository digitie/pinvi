"""소유자 일정 알림 큐. 한 DB transaction이 한 대상의 한 chunk만 전송한다.

SKIP LOCKED claim의 transaction 안에서 동의→여행→대상을 검사·잠근다.
ACK 지점을 commit한 뒤 다음 chunk를 처리하므로 다른 claim의 잠금을 풀지 않는다.
Telegram에 idempotency key가 없어 provider 수락 후 DB ACK 유실은 중복 가능하다.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram import TelegramError, mask_token
from app.core.config import settings
from app.models.poi import TripDayPoi
from app.models.telegram_notification import (
    TelegramDelivery,
    TelegramNotification,
    TelegramPreferences,
)
from app.models.telegram_target import TelegramTarget
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.trip_telegram_target import TripTelegramTarget
from app.models.user import User
from app.schemas.telegram_notifications import (
    TelegramDeliveryResponse,
    TelegramNotificationResponse,
    TelegramPreferencesBody,
    TelegramSendRequest,
)
from app.services import telegram_notify
from app.services.telegram_itinerary import itinerary_text, split_message
from app.services.telegram_metrics import record_step
from app.services.telegram_outbox import MAX_TELEGRAM_ATTEMPTS, _retry_delay
from app.services.trip import TripNotFoundError, TripPermissionError, TripValidationError

_SAFE_ERRORS = {
    "missing_chat_id": "Telegram 대상 ID가 없습니다.",
    "invalid_chat": "Telegram 대상을 찾을 수 없습니다. 대상 ID와 봇 참여 여부를 확인하세요.",
    "invalid_topic": "Telegram 주제를 찾을 수 없습니다. 주제 ID를 확인하세요.",
    "bot_forbidden": "봇의 전송 권한이 없습니다. 대화방에서 봇 권한을 확인하고 대상을 다시 검증하세요.",
    "rate_limited": "Telegram 요청 한도에 도달했습니다. 표시된 시각 이후 재시도합니다.",
    "network_error": "Telegram 연결에 실패했습니다. 잠시 후 재시도합니다.",
    "unknown_error": "Telegram이 올바른 응답을 반환하지 않았습니다.",
}


async def owned_trip_locked(db: AsyncSession, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip:
    trip = await db.scalar(
        select(Trip)
        .where(Trip.trip_id == trip_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if trip is None or trip.deleted_at is not None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    if trip.owner_user_id != user_id:
        raise TripPermissionError("여행 소유자만 알림을 보낼 수 있습니다.")
    return trip


async def preferences(
    db: AsyncSession, user_id: uuid.UUID, *, lock: bool = False
) -> TelegramPreferences | None:
    query = select(TelegramPreferences).where(TelegramPreferences.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row: TelegramPreferences | None = await db.scalar(query)
    return row


def preferences_body(row: TelegramPreferences | None) -> TelegramPreferencesBody:
    if row is None:
        return TelegramPreferencesBody()
    return TelegramPreferencesBody(
        daily_enabled=row.daily_enabled,
        weekly_enabled=row.weekly_enabled,
        send_time=row.send_time,
        weekly_day=row.weekly_day,
        weekly_target_id=row.weekly_target_id,
    )


async def save_preferences(
    db: AsyncSession, user_id: uuid.UUID, body: TelegramPreferencesBody
) -> TelegramPreferences:
    if not body.weekly_enabled:
        # 오래된 주간 대상이 수신 해제(다른 정상 대상의 일간 포함)를 막지 않는다.
        body = body.model_copy(update={"weekly_target_id": None})
    await db.execute(
        insert(TelegramPreferences)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    row = await preferences(db, user_id, lock=True)
    assert row is not None
    if body.weekly_target_id is not None:
        target = await db.scalar(
            select(TelegramTarget)
            .where(TelegramTarget.id == body.weekly_target_id, TelegramTarget.user_id == user_id)
            .with_for_update()
        )
        if (
            target is None
            or target.deleted_at is not None
            or not target.is_enabled
            or target.last_verified_at is None
        ):
            raise TripValidationError("활성·검증된 본인 Telegram 대상을 선택하세요.")
    if preferences_body(row) != body:
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.generation = uuid.uuid4()
    await db.flush()
    return row


async def linked_targets(
    db: AsyncSession, trip: Trip
) -> list[tuple[TelegramTarget, TripTelegramTarget]]:
    result = await db.execute(
        select(TelegramTarget, TripTelegramTarget)
        .join(TripTelegramTarget, TripTelegramTarget.telegram_target_id == TelegramTarget.id)
        .where(
            TripTelegramTarget.trip_id == trip.trip_id,
            TelegramTarget.user_id == trip.owner_user_id,
            TelegramTarget.deleted_at.is_(None),
            TelegramTarget.is_enabled.is_(True),
            TelegramTarget.last_verified_at.is_not(None),
        )
        .order_by(TelegramTarget.id)
    )
    return [(target, link) for target, link in result.all()]


async def enqueue(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: str,
    category: str,
    fingerprint: str,
    trip_ids: list[uuid.UUID],
    message: str,
    recipients: list[tuple[TelegramTarget, TripTelegramTarget | None]],
    consent_generation: uuid.UUID | None = None,
) -> TelegramNotification:
    chunks = split_message(message)
    if len(chunks) > 256:
        raise TripValidationError("일정이 너무 깁니다. 특정 일자를 선택해 보내세요.")
    notification_id = await db.scalar(
        insert(TelegramNotification)
        .values(
            user_id=user_id,
            occurrence_key=key,
            category=category,
            request_fingerprint=fingerprint,
            trip_ids=[str(value) for value in trip_ids],
            chunks=chunks,
            consent_generation=consent_generation,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "occurrence_key"])
        .returning(TelegramNotification.id)
    )
    if notification_id is None:
        existing = await db.scalar(
            select(TelegramNotification).where(
                TelegramNotification.user_id == user_id, TelegramNotification.occurrence_key == key
            )
        )
        assert existing is not None
        if existing.request_fingerprint != fingerprint:
            raise TripValidationError("같은 요청 ID를 다른 알림에 사용할 수 없습니다.")
        return existing
    for target, link in recipients:
        db.add(
            TelegramDelivery(
                notification_id=notification_id,
                target_id=target.id,
                target_generation=target.generation,
                link_generation=link.generation if link else None,
            )
        )
    await db.flush()
    result = await db.get(TelegramNotification, notification_id)
    assert result is not None
    return result


async def itinerary(db: AsyncSession, trip: Trip, day_index: int | None = None) -> str:
    days = list(
        (
            await db.scalars(
                select(TripDay).where(TripDay.trip_id == trip.trip_id).order_by(TripDay.day_index)
            )
        ).all()
    )
    if day_index is not None:
        days = [day for day in days if day.day_index == day_index]
        if not days:
            raise TripNotFoundError("일자를 찾을 수 없습니다.")
    pois = list(
        (
            await db.scalars(
                select(TripDayPoi)
                .where(TripDayPoi.trip_id == trip.trip_id, TripDayPoi.deleted_at.is_(None))
                .order_by(TripDayPoi.day_index, TripDayPoi.sort_order)
            )
        ).all()
    )
    return itinerary_text(trip, days, pois)


async def manual_send(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID, body: TelegramSendRequest
) -> TelegramNotification:
    trip = await owned_trip_locked(db, trip_id, user_id)
    fingerprint = hashlib.sha256(f"{trip_id}:{body.scope}:{body.day_index}".encode()).hexdigest()
    # 재시도에서 최초 스냅샷을 보존하며 연결이 없어져도 같은 응답을 제공한다.
    existing = await db.scalar(
        select(TelegramNotification).where(
            TelegramNotification.user_id == user_id,
            TelegramNotification.occurrence_key == f"manual:{body.request_id}",
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise TripValidationError("같은 요청 ID를 다른 알림에 사용할 수 없습니다.")
        return existing
    targets = await linked_targets(db, trip)
    if not targets:
        raise TripValidationError("먼저 활성·검증된 Telegram 대상을 여행에 연결하세요.")
    return await enqueue(
        db,
        user_id=user_id,
        key=f"manual:{body.request_id}",
        category="itinerary",
        fingerprint=fingerprint,
        trip_ids=[trip_id],
        message=await itinerary(db, trip, body.day_index),
        recipients=[(target, link) for target, link in targets],
    )


async def notification_response(
    db: AsyncSession, row: TelegramNotification
) -> TelegramNotificationResponse:
    deliveries = list(
        (
            await db.scalars(
                select(TelegramDelivery)
                .where(TelegramDelivery.notification_id == row.id)
                .order_by(TelegramDelivery.id)
            )
        ).all()
    )
    return TelegramNotificationResponse(
        id=row.id,
        category=row.category,
        trip_ids=[uuid.UUID(value) for value in row.trip_ids],
        created_at=row.created_at,
        deliveries=[
            TelegramDeliveryResponse(
                id=d.id,
                target_id=d.target_id,
                status=d.status,
                sent_chunks=d.next_chunk,
                total_chunks=len(row.chunks),
                attempts=d.attempts,
                retry_at=d.scheduled_at if d.status == "pending" else None,
                error_code=d.error_code,
                error_message=d.error_message,
            )
            for d in deliveries
        ],
    )


async def _guard(
    db: AsyncSession, row: TelegramNotification, delivery: TelegramDelivery
) -> TelegramTarget | None:
    user = await db.get(User, row.user_id, populate_existing=True)
    if user is None or not user.is_active or user.deleted_at is not None or user.status != "active":
        return None
    if row.consent_generation is not None:
        pref = await preferences(db, row.user_id, lock=True)
        flag = {
            "daily_brief": "daily_enabled",
            "weekly_summary": "weekly_enabled",
        }.get(row.category)
        if (
            pref is None
            or flag is None
            or not getattr(pref, flag)
            or pref.generation != row.consent_generation
        ):
            return None
        if row.category == "weekly_summary" and pref.weekly_target_id != delivery.target_id:
            return None
    for trip_id in sorted(row.trip_ids):
        trip = await db.scalar(
            select(Trip)
            .where(Trip.trip_id == uuid.UUID(trip_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if trip is None or trip.deleted_at is not None or trip.owner_user_id != row.user_id:
            return None
    target = await db.scalar(
        select(TelegramTarget)
        .where(TelegramTarget.id == delivery.target_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        target is None
        or target.user_id != row.user_id
        or target.deleted_at is not None
        or not target.is_enabled
        or target.last_verified_at is None
        or target.generation != delivery.target_generation
    ):
        return None
    if delivery.link_generation is not None:
        if len(row.trip_ids) != 1:
            return None
        link = await db.get(
            TripTelegramTarget, (uuid.UUID(row.trip_ids[0]), target.id), populate_existing=True
        )
        if link is None or link.generation != delivery.link_generation:
            return None
    return target


async def process_one(db: AsyncSession, *, now: datetime | None = None) -> bool:
    """한 chunk만 claim한다. DB commit 실패·취소는 호출자 rollback으로 잠금을 반납한다."""
    current = now or datetime.now(UTC)
    started = time.monotonic()
    delivery = await db.scalar(
        select(TelegramDelivery)
        .where(TelegramDelivery.status == "pending", TelegramDelivery.scheduled_at <= current)
        .order_by(TelegramDelivery.scheduled_at, TelegramDelivery.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if delivery is None:
        return False
    row = await db.get(TelegramNotification, delivery.notification_id)
    assert row is not None
    target = await _guard(db, row, delivery)
    if target is None:
        delivery.status, delivery.error_code = "skipped", "destination_changed"
        delivery.error_message = "대상·연결·동의·여행 권한이 바뀌어 전송하지 않았습니다."
    elif not settings.pinvi_telegram_bot_token_default:
        delivery.status, delivery.error_code = "failed", "bot_not_configured"
        delivery.error_message = "Telegram 봇이 설정되지 않았습니다. 관리자에게 문의하세요."
    else:
        client = telegram_notify._make_client()
        delivery.attempts += 1
        try:
            await client.send_to_target(
                settings.pinvi_telegram_bot_token_default,
                target.telegram_chat_id,
                row.chunks[delivery.next_chunk],
                thread_id=target.telegram_message_thread_id,
                parse_mode=None,
            )
        except TelegramError as exc:
            code = exc.code if exc.code in _SAFE_ERRORS else "unknown_error"
            token = settings.pinvi_telegram_bot_token_default
            detail = mask_token(str(exc).replace(token, "***")).replace(
                target.telegram_chat_id, "[대상]"
            )
            delivery.error_code = code
            delivery.error_message = _SAFE_ERRORS[code] + (
                f" Telegram: {detail[:240]}" if detail else ""
            )
            retry = exc.retry_after if type(exc.retry_after) is int and exc.retry_after > 0 else 0
            if (
                code not in {"rate_limited", "network_error", "unknown_error"}
                or delivery.attempts >= MAX_TELEGRAM_ATTEMPTS
            ):
                delivery.status = "failed"
            else:
                try:
                    delivery.scheduled_at = current + timedelta(
                        seconds=time.monotonic()
                        - started
                        + max(_retry_delay(delivery.attempts), retry)
                    )
                except OverflowError:
                    delivery.status = "failed"
            if code == "bot_forbidden":
                target.is_enabled = False
                target.generation = uuid.uuid4()
            target.last_send_status = f"failed:{code}"
        except Exception:
            # 원문 SQL/transport traceback은 사용자에게 공개하지 않는다.
            delivery.status, delivery.error_code = "failed", "delivery_error"
            delivery.error_message = "알림 처리에 실패했습니다. 관리자에게 문의하세요."
        else:
            delivery.next_chunk += 1
            delivery.attempts = 0
            delivery.error_code = delivery.error_message = None
            target.last_send_status = "ok"
            if delivery.next_chunk == len(row.chunks):
                delivery.status, delivery.sent_at = "sent", current
            else:
                delivery.scheduled_at = current + timedelta(seconds=3)
        finally:
            await client.aclose()
    category, final_status, has_error = (
        row.category,
        delivery.status,
        delivery.error_code is not None,
    )
    await db.commit()
    record_step(
        category, status=final_status, has_error=has_error, duration=time.monotonic() - started
    )
    return True
