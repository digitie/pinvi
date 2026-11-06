"""소유자 일정 알림 큐. 한 번의 처리가 한 대상의 한 chunk만 전송한다.

SKIP LOCKED claim의 transaction 안에서 동의→여행→대상을 검사·잠근 뒤 짧은 lease를 commit하고
잠금 없이 Telegram을 호출한다. 결과는 새 transaction에서 같은 lease token일 때만 기록한다.
Telegram에 idempotency key가 없어 provider 수락 후 DB ACK 유실은 중복 가능하다.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import and_, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.clients.telegram import TelegramError, mask_token
from app.core.config import settings
from app.models.poi import TripDayPoi
from app.models.telegram_notification import (
    TelegramDelivery,
    TelegramNotification,
    TelegramPreferences,
    TelegramWeatherObservation,
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
from app.services.telegram_itinerary import KST, effective_date, itinerary_text, split_message
from app.services.telegram_metrics import record_step
from app.services.telegram_outbox import MAX_TELEGRAM_ATTEMPTS, _retry_delay
from app.services.trip import TripNotFoundError, TripPermissionError, TripValidationError

logger = logging.getLogger(__name__)

_SAFE_ERRORS = {
    "missing_chat_id": "Telegram 대상 ID가 없습니다.",
    "invalid_chat": "Telegram 대상을 찾을 수 없습니다. 대상 ID와 봇 참여 여부를 확인하세요.",
    "invalid_topic": "Telegram 주제를 찾을 수 없습니다. 주제 ID를 확인하세요.",
    "bot_forbidden": "봇의 전송 권한이 없습니다. 대화방에서 봇 권한을 확인하고 대상을 다시 검증하세요.",
    "rate_limited": "Telegram 요청 한도에 도달했습니다. 표시된 시각 이후 재시도합니다.",
    "network_error": "Telegram 연결에 실패했습니다. 잠시 후 재시도합니다.",
    "unknown_error": "Telegram이 올바른 응답을 반환하지 않았습니다.",
}


class TelegramMessageTooLarge(TripValidationError):
    code = "TELEGRAM_MESSAGE_TOO_LARGE"


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
        weather_enabled=row.weather_enabled,
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
    if "weather_enabled" not in body.model_fields_set:
        body = body.model_copy(update={"weather_enabled": row.weather_enabled})
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
            if row.weather_enabled and not body.weather_enabled:
                # 유효하지 않은 별도 주간 목적지가 독립적인 특보 철회를 막지 않는다.
                body = body.model_copy(update={"weekly_enabled": False, "weekly_target_id": None})
            else:
                raise TripValidationError("활성·검증된 본인 Telegram 대상을 선택하세요.")
    if row.weather_enabled != body.weather_enabled:
        row.weather_enabled_at = datetime.now(UTC) if body.weather_enabled else None
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
    schedule_snapshot: dict[str, object] | None = None,
    expires_at: datetime | None = None,
) -> TelegramNotification:
    chunks = split_message(message)
    if len(chunks) > 256:
        raise TelegramMessageTooLarge("일정이 너무 깁니다. 특정 일자를 선택해 보내세요.")
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
            schedule_snapshot=schedule_snapshot or {},
            expires_at=expires_at,
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


# 한 사용자가 대기 중인 수동 일정 전송의 상한. 공용 봇 큐에서 다른 사용자의 기한 있는
# 특보·브리프가 밀려 만료되지 않게 한다. 같은 request_id 재시도는 상한과 무관하다.
MANUAL_PENDING_LIMIT = 3


class TelegramSendBacklogError(TripValidationError):
    code = "TELEGRAM_SEND_BACKLOG"


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
    # 사용자 행 잠금으로 같은 사용자의 다른 여행 전송과 상한 확인을 직렬화한다.
    await db.scalar(select(User).where(User.user_id == user_id).with_for_update(key_share=True))
    backlog = await db.scalar(
        select(func.count(func.distinct(TelegramNotification.id)))
        .select_from(TelegramNotification)
        .join(TelegramDelivery, TelegramDelivery.notification_id == TelegramNotification.id)
        .where(
            TelegramNotification.user_id == user_id,
            TelegramNotification.category == "itinerary",
            TelegramDelivery.status == "pending",
        )
    )
    if (backlog or 0) >= MANUAL_PENDING_LIMIT:
        raise TelegramSendBacklogError(
            "이전 일정 전송이 아직 진행 중입니다. 발송 내역에서 완료를 확인한 뒤 다시 보내세요."
        )
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
        error_code=row.error_code,
        error_message=row.error_message,
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
    db: AsyncSession, row: TelegramNotification, delivery: TelegramDelivery, *, now: datetime
) -> tuple[TelegramTarget | None, str | None]:
    if row.category in {"daily_brief", "weekly_summary"}:
        if row.expires_at is None or now >= row.expires_at:
            return None, "schedule_expired"
        if row.schedule_snapshot.get("reference_date") != now.astimezone(KST).date().isoformat():
            return None, "schedule_expired"
        expected_trips = row.schedule_snapshot.get("trips")
        if not isinstance(expected_trips, dict) or set(expected_trips) != set(row.trip_ids):
            return None, "schedule_changed"
    user = await db.get(User, row.user_id, populate_existing=True)
    if user is None or not user.is_active or user.deleted_at is not None or user.status != "active":
        return None, "destination_changed"
    if row.consent_generation is not None:
        pref = await preferences(db, row.user_id, lock=True)
        flag = {
            "weather_alert": "weather_enabled",
            "daily_brief": "daily_enabled",
            "weekly_summary": "weekly_enabled",
        }.get(row.category)
        if (
            pref is None
            or flag is None
            or not getattr(pref, flag)
            or pref.generation != row.consent_generation
        ):
            return None, "destination_changed"
        if row.category == "weekly_summary" and pref.weekly_target_id != delivery.target_id:
            return None, "destination_changed"
    for trip_id in sorted(row.trip_ids):
        trip = await db.scalar(
            select(Trip)
            .where(Trip.trip_id == uuid.UUID(trip_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if trip is None or trip.deleted_at is not None or trip.owner_user_id != row.user_id:
            return None, "destination_changed"
        if row.category == "weather_alert":
            snapshot = row.schedule_snapshot
            if (
                len(row.trip_ids) != 1
                or snapshot.get("trip_version") != trip.version
                or snapshot.get("bjd_code") != trip.primary_region_code
                or trip.start_date is None
                or trip.end_date is None
                or not trip.start_date <= now.astimezone(KST).date() <= trip.end_date
            ):
                return None, "schedule_changed"
            announcement = snapshot.get("announcement_id")
            if not isinstance(announcement, str):
                return None, "weather_observation_changed"
            observation = await db.get(
                TelegramWeatherObservation, (trip.trip_id, announcement), populate_existing=True
            )
            if (
                observation is None
                or str(observation.generation) != snapshot.get("observation_generation")
                or observation.event_id != snapshot.get("event_id")
                or (observation.ambiguous and not observation.cancelled)
            ):
                return None, "weather_observation_changed"
        if row.category in {"daily_brief", "weekly_summary"}:
            expected = row.schedule_snapshot["trips"][trip_id]
            if not isinstance(expected, dict) or (
                expected.get("start_date")
                != (trip.start_date.isoformat() if trip.start_date else None)
                or expected.get("end_date")
                != (trip.end_date.isoformat() if trip.end_date else None)
            ):
                return None, "schedule_changed"
            if row.category == "daily_brief":
                index = expected.get("day_index")
                if type(index) is not int:
                    return None, "schedule_changed"
                day = await db.get(TripDay, (trip.trip_id, index), populate_existing=True)
                if day is None:
                    return None, "schedule_changed"
                current_date = effective_date(trip, day)
                if expected.get("effective_date") != (
                    current_date.isoformat() if current_date else None
                ):
                    return None, "schedule_changed"
    # Trip→User 순서의 NO KEY UPDATE로 계정 철회 commit과 전송을 직렬화한다.
    # 초반 읽기 뒤 다른 잠금을 기다렸을 수 있으므로 반드시 최신 값을 다시 채운다.
    user = await db.scalar(
        select(User)
        .where(User.user_id == row.user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active or user.deleted_at is not None or user.status != "active":
        return None, "account_inactive"
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
        return None, "destination_changed"
    if delivery.link_generation is not None:
        if len(row.trip_ids) != 1:
            return None, "destination_changed"
        link = await db.get(
            TripTelegramTarget, (uuid.UUID(row.trip_ids[0]), target.id), populate_existing=True
        )
        if link is None or link.generation != delivery.link_generation:
            return None, "destination_changed"
    return target, None


# Telegram 호출 동안 같은 chunk를 다른 worker가 다시 claim하지 않게 하는 lease(초).
# 전송 timeout(기본 5초)보다 충분히 길다. 결과를 기록하지 못한 채 프로세스가 죽으면 이 시간 뒤
# 다시 보낸다 — provider 수락 뒤 ACK 유실과 같은 기존 중복 가능성이며 새로 생기지 않는다.
CLAIM_LEASE_SECONDS = 60

_REJECTIONS = {
    "account_inactive": "계정이 비활성화되어 알림을 보내지 않았습니다.",
    "schedule_expired": "알림 유효 시간이 지나 전송하지 않았습니다.",
    "weather_observation_changed": "공식 발표의 취소·상충 관측이 확인되어 이전 알림을 전송하지 않았습니다.",
    "schedule_changed": "여행·일자 날짜가 바뀌어 예약 알림을 전송하지 않았습니다.",
}


def _due(current: datetime) -> ColumnElement[bool]:
    # 만료된 예약은 retry 시각 전에도 닫는다. 단 전송 중(lease)인 chunk는 결과 기록을 기다린다.
    return and_(
        TelegramDelivery.status == "pending",
        or_(
            TelegramDelivery.scheduled_at <= current,
            and_(
                TelegramDelivery.claim_token.is_(None),
                TelegramNotification.expires_at <= current,
            ),
        ),
    )


async def fair_batch(db: AsyncSession, *, now: datetime, limit: int) -> list[uuid.UUID]:
    """사용자별 순번(rank)을 먼저 정렬해 한 사용자의 backlog가 다른 사용자의 기한 있는 알림을 밀지 않게 한다.

    각 사용자의 첫 chunk가 모두 나간 뒤에 두 번째 chunk가 나간다. 다른 사용자가 없으면 한 사용자가
    한 바퀴를 모두 쓴다(처리량 제한 없음). 대기 사용자가 limit보다 많으면 각자의 가장 오래된 chunk
    순서로 limit명까지 처리하고 나머지는 다음 바퀴에 처리한다.
    잠그지 않는 계획일 뿐이다. 실제 claim은 process_one이 SKIP LOCKED로 다시 확인한다.
    """
    rank = (
        func.row_number()
        .over(
            partition_by=TelegramNotification.user_id,
            order_by=(TelegramDelivery.scheduled_at, TelegramDelivery.id),
        )
        .label("rank")
    )
    ranked = (
        select(TelegramDelivery.id.label("id"), TelegramDelivery.scheduled_at.label("at"), rank)
        .join(TelegramNotification, TelegramNotification.id == TelegramDelivery.notification_id)
        .where(_due(now))
        .subquery()
    )
    ids = await db.scalars(
        select(ranked.c.id).order_by(ranked.c.rank, ranked.c.at, ranked.c.id).limit(limit)
    )
    result = list(ids.all())
    await db.commit()
    return result


async def _release_claim(
    delivery_id: uuid.UUID, lease: uuid.UUID, scheduled_at: datetime, attempts: int
) -> None:
    from app.db import session as db_session

    async with db_session.async_session_factory() as db:
        await db.execute(
            update(TelegramDelivery)
            .where(TelegramDelivery.id == delivery_id, TelegramDelivery.claim_token == lease)
            .values(claim_token=None, scheduled_at=scheduled_at, attempts=attempts)
        )
        await db.commit()


async def process_one(
    db: AsyncSession, *, now: datetime | None = None, delivery_id: uuid.UUID | None = None
) -> bool:
    """한 chunk만 처리한다.

    정책 확인은 claim transaction 안에서 Trip→User→대상 잠금으로 한다. 보낼 내용과 대상을 정한 뒤
    lease를 commit해 잠금을 모두 풀고 Telegram을 호출한다 — 느린 Telegram 응답이 여행 편집·동의 철회를
    막지 않는다. 결과는 새 transaction에서 같은 lease token일 때만 기록한다. 따라서 정책 확인 commit
    뒤 전송 직전까지 사이의 철회는 이미 결정된 그 한 chunk를 막지 못한다(전송 중 철회와 같다).
    """
    current = now or datetime.now(UTC)
    started = monotonic()
    query = (
        select(TelegramDelivery)
        .join(TelegramNotification, TelegramNotification.id == TelegramDelivery.notification_id)
        .where(_due(current))
    )
    if delivery_id is not None:
        query = query.where(TelegramDelivery.id == delivery_id)
    delivery = await db.scalar(
        query.order_by(TelegramDelivery.scheduled_at, TelegramDelivery.id)
        .limit(1)
        .with_for_update(of=TelegramDelivery, skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if delivery is None:
        await db.rollback()
        return False
    row = await db.get(TelegramNotification, delivery.notification_id)
    assert row is not None
    category = row.category
    target, rejection = await _guard(
        db, row, delivery, now=current + timedelta(seconds=monotonic() - started)
    )
    # 정책 잠금 대기 중 날짜가 바뀌었을 수 있어 HTTP 직전에 다시 확인한다.
    observed = current + timedelta(seconds=monotonic() - started)
    if target is not None and row.expires_at is not None and observed >= row.expires_at:
        target, rejection = None, "schedule_expired"
    token = settings.pinvi_telegram_bot_token_default
    if target is None or not token:
        if target is None:
            delivery.status, delivery.error_code = "skipped", rejection
            delivery.error_message = _REJECTIONS.get(
                rejection or "", "대상·연결·동의·여행 권한이 바뀌어 전송하지 않았습니다."
            )
        else:
            delivery.status, delivery.error_code = "failed", "bot_not_configured"
            delivery.error_message = "Telegram 봇이 설정되지 않았습니다. 관리자에게 문의하세요."
        delivery.claim_token = None
        final_status, has_error = delivery.status, delivery.error_code is not None
        await db.commit()
        record_step(
            category, status=final_status, has_error=has_error, duration=monotonic() - started
        )
        return True

    # 보낼 내용·대상을 고정하고 lease를 commit한다. 이후에는 어떤 정책 잠금도 쥐지 않는다.
    claimed_id, target_id, target_generation = delivery.id, target.id, target.generation
    chat_id, thread_id = target.telegram_chat_id, target.telegram_message_thread_id
    chunk, total = row.chunks[delivery.next_chunk], len(row.chunks)
    lease, previous_at, previous_attempts = uuid.uuid4(), delivery.scheduled_at, delivery.attempts
    delivery.claim_token = lease
    delivery.attempts += 1
    attempts = delivery.attempts
    delivery.scheduled_at = observed + timedelta(seconds=CLAIM_LEASE_SECONDS)
    await db.commit()

    failure: TelegramError | None = None
    unexpected = False
    client = telegram_notify._make_client()
    try:
        await client.send_to_target(token, chat_id, chunk, thread_id=thread_id, parse_mode=None)
    except TelegramError as exc:
        failure = exc
    except asyncio.CancelledError:
        # 취소된 전송의 결과는 알 수 없다. 이전과 같이 claim을 즉시 돌려 다음 worker가 재시도한다.
        release = asyncio.create_task(
            _release_claim(claimed_id, lease, previous_at, previous_attempts)
        )
        try:
            await asyncio.shield(release)
        except asyncio.CancelledError:
            await release
        raise
    except Exception:
        unexpected = True
    finally:
        await client.aclose()

    finished = current + timedelta(seconds=monotonic() - started)
    # 결과 기록이 잠금을 오래 기다려 lease를 넘기면 다른 worker가 같은 chunk를 다시 보낸다.
    await db.execute(text("SET LOCAL lock_timeout = '5s'"))
    delivery = await db.scalar(
        select(TelegramDelivery)
        .where(
            TelegramDelivery.id == claimed_id,
            TelegramDelivery.claim_token == lease,
            TelegramDelivery.status == "pending",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if delivery is None:
        # lease가 만료되어 다른 worker가 인수했다. 그쪽 결과를 덮어쓰지 않는다.
        await db.rollback()
        return True
    # 비키 열만 바꾸므로 NO KEY UPDATE로 충분하다. enqueue의 FK 검사(KEY SHARE)와 충돌하지 않는다.
    target = await db.scalar(
        select(TelegramTarget)
        .where(TelegramTarget.id == target_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if (
        target is not None
        and (
            target.generation != target_generation
            or target.deleted_at is not None
            or not target.is_enabled
        )
    ):
        # 전송 중 재검증·삭제·비활성화된 대상의 새 상태를 이 결과로 덮어쓰지 않는다.
        target = None
    delivery.claim_token = None
    if unexpected:
        # 원문 SQL/transport traceback은 사용자에게 공개하지 않는다.
        delivery.status, delivery.error_code = "failed", "delivery_error"
        delivery.error_message = "알림 처리에 실패했습니다. 관리자에게 문의하세요."
    elif failure is not None:
        code = failure.code if failure.code in _SAFE_ERRORS else "unknown_error"
        detail = mask_token(str(failure).replace(token, "***")).replace(chat_id, "[대상]")
        delivery.error_code = code
        delivery.error_message = _SAFE_ERRORS[code] + (
            f" Telegram: {detail[:240]}" if detail else ""
        )
        retry = (
            failure.retry_after
            if type(failure.retry_after) is int and failure.retry_after > 0
            else 0
        )
        if (
            code not in {"rate_limited", "network_error", "unknown_error"}
            or attempts >= MAX_TELEGRAM_ATTEMPTS
        ):
            delivery.status = "failed"
        else:
            try:
                delivery.scheduled_at = finished + timedelta(
                    seconds=max(_retry_delay(attempts), retry)
                )
            except OverflowError:
                delivery.status = "failed"
        if target is not None:
            if code == "bot_forbidden":
                target.is_enabled = False
                target.generation = uuid.uuid4()
            target.last_send_status = f"failed:{code}"
    else:
        delivery.next_chunk += 1
        delivery.attempts = 0
        delivery.error_code = delivery.error_message = None
        if target is not None:
            target.last_send_status = "ok"
        if delivery.next_chunk >= total:
            delivery.status, delivery.sent_at = "sent", finished
        else:
            delivery.scheduled_at = finished + timedelta(seconds=3)
    final_status, has_error = delivery.status, delivery.error_code is not None
    await db.commit()
    record_step(category, status=final_status, has_error=has_error, duration=monotonic() - started)
    return True


async def drain_fair(*, now: datetime | None = None, limit: int) -> int:
    """사용자 순번 순서로 한 바퀴를 처리한다. 처리한 chunk 수를 돌려준다."""
    from app.db import session as db_session

    current = now or datetime.now(UTC)
    async with db_session.async_session_factory() as db:
        planned = await fair_batch(db, now=current, limit=limit)
    processed = 0
    for delivery_id in planned:
        try:
            async with db_session.async_session_factory() as db:
                if await process_one(db, now=now, delivery_id=delivery_id):
                    processed += 1
        except Exception as exc:
            # 한 건의 잠금 timeout·deadlock·손상 행이 같은 바퀴 뒤 사용자들을 멈추지 않게 한다.
            # 미커밋 변경은 세션 종료로 롤백되고 lease가 있으면 만료 뒤 다시 처리된다.
            logger.warning("telegram delivery step failed: %s", type(exc).__name__)
    return processed


async def purge_expired_bodies(
    db: AsyncSession, *, now: datetime | None = None, limit: int = 500
) -> int:
    """보존 기한이 지난, 대기 중 전송이 없는 알림의 본문·스냅샷·전송 오류 상세를 지운다.

    발생키(중복 방지)·분류·상태·시각·오류 코드는 남긴다. chunk 개수는 이력의 진행률 표시를
    위해 빈 문자열로 유지한다.
    """
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=settings.pinvi_telegram_notification_retention_days)
    pending = exists(
        select(TelegramDelivery.id).where(
            TelegramDelivery.notification_id == TelegramNotification.id,
            TelegramDelivery.status == "pending",
        )
    )
    ids = list(
        (
            await db.scalars(
                select(TelegramNotification.id)
                .where(
                    TelegramNotification.body_purged_at.is_(None),
                    TelegramNotification.created_at <= cutoff,
                    ~pending,
                )
                .order_by(TelegramNotification.created_at, TelegramNotification.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    if not ids:
        await db.rollback()
        return 0
    blank = text(
        "(SELECT COALESCE(jsonb_agg(to_jsonb(''::text)), '[]'::jsonb) "
        "FROM jsonb_array_elements(app.telegram_notifications.chunks))"
    )
    await db.execute(
        update(TelegramNotification)
        .where(TelegramNotification.id.in_(ids))
        .values(chunks=blank, schedule_snapshot=text("'{}'::jsonb"), body_purged_at=current)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(TelegramDelivery)
        .where(
            TelegramDelivery.notification_id.in_(ids),
            TelegramDelivery.error_message.is_not(None),
        )
        .values(error_message=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return len(ids)
