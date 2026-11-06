"""KST 일간·주간 발생키 planner. Dagster는 좁은 인증 HTTP 경계만 호출한다."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_weather import create_map_weather_client
from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.core.config import settings
from app.db import session as db_session
from app.db.session import SESSION_TIMEOUT_SERVER_SETTINGS
from app.models.kasi import TripDayRiseSet
from app.models.poi import TripDayPoi
from app.models.telegram_notification import TelegramNotification, TelegramPreferences
from app.models.telegram_target import TelegramTarget
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.services.telegram_itinerary import KST, effective_date, local_time, summary
from app.services.telegram_metrics import PLANNING_FAILURES
from app.services.telegram_notifications import (
    TelegramMessageTooLarge,
    enqueue,
    itinerary,
    linked_targets,
    preferences,
)
from app.services.telegram_weather import plan_weather, prepare_weather
from app.services.trip_weather_batch import (
    build_trip_weather_via_kor_travel_map,
    build_trip_weather_via_kor_travel_weather,
)

logger = logging.getLogger(__name__)


def weather_summary(cards: dict[str, dict[str, Any]]) -> str:
    # API가 이미 투영한 사람용 metric_name만 사용하며 원시 provider key를 새로 해석하지 않는다.
    lines: list[str] = []
    for card in cards.values():
        stale = " (오래된 정보)" if card.get("is_stale") else ""
        for metric in card.get("metrics", []):
            name = metric.get("metric_name")
            value = metric.get("value_text")
            if value is None:
                value = metric.get("value_number")
            if name and value is not None:
                line = f"{summary(str(name), 40)} {summary(str(value), 80)}{metric.get('unit') or ''}{stale}"
                if line not in lines:
                    lines.append(line)
    return "날씨: " + (" · ".join(lines[:6]) if lines else "정보를 확인하지 못했습니다.")


async def daily_context(
    db: AsyncSession,
    trip: Trip,
    day: TripDay,
    *,
    map_client: KorTravelMapClient | None,
    weather_client: KorTravelWeatherClient | None,
) -> str:
    pois = list(
        (
            await db.scalars(
                select(TripDayPoi).where(
                    TripDayPoi.trip_id == trip.trip_id,
                    TripDayPoi.day_index == day.day_index,
                    TripDayPoi.deleted_at.is_(None),
                )
            )
        ).all()
    )
    target_date = effective_date(trip, day)
    cards: dict[int, dict[str, dict[str, Any]]] = {}
    # 이 단계는 정책 잠금·업무 쓰기가 없는 준비용 읽기 세션이다.
    # 기존 helper가 같은 세션을 commit해 연결을 반납하고 HTTP를 수행한다.
    if (
        settings.pinvi_kor_travel_map_weather_enabled
        and map_client is not None
        and map_client.has_service_token
    ):
        _, cards = await build_trip_weather_via_kor_travel_map(
            db,
            pois=pois,
            day_effective_date={day.day_index: target_date},
            map_client=create_map_weather_client(map_client),
            weather_client=weather_client,
            budget_seconds=8,
        )
    elif not settings.pinvi_kor_travel_map_weather_enabled and weather_client is not None:
        _, cards = await build_trip_weather_via_kor_travel_weather(
            db,
            pois=pois,
            day_effective_date={day.day_index: target_date},
            weather_client=weather_client,
            budget_seconds=8,
        )
    return weather_summary(cards.get(day.day_index, {}))


def _daily_key(trip_id: uuid.UUID, target_date: date, today: date) -> str:
    return f"daily:{trip_id}:{target_date}:{'today' if target_date == today else 'eve'}"


async def _prepare_daily_contexts(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime,
    map_client: KorTravelMapClient | None,
    weather_client: KorTravelWeatherClient | None,
) -> dict[tuple[uuid.UUID, int, date], str]:
    """외부 조회 중에는 동의·Trip row를 잠그지 않는다. 적재 단계에서 새 동의를 읽는다."""
    pref = await preferences(db, user_id)
    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None or user.status != "active":
        return {}
    local = now.astimezone(KST)
    if pref is None or not pref.daily_enabled or local.strftime("%H:%M") < pref.send_time:
        return {}
    today = local.date()
    contexts: dict[tuple[uuid.UUID, int, date], str] = {}
    rows = await db.execute(
        select(Trip, TripDay)
        .join(TripDay, TripDay.trip_id == Trip.trip_id)
        .where(Trip.owner_user_id == user_id, Trip.deleted_at.is_(None))
        .order_by(Trip.trip_id, TripDay.day_index)
    )
    for trip, day in rows:
        target_date = effective_date(trip, day)
        if target_date is None or target_date not in (today, today + timedelta(days=1)):
            continue
        key = _daily_key(trip.trip_id, target_date, today)
        existing = await db.scalar(
            select(TelegramNotification.id).where(
                TelegramNotification.user_id == user_id, TelegramNotification.occurrence_key == key
            )
        )
        if existing is None and await linked_targets(db, trip):
            contexts[(trip.trip_id, day.day_index, target_date)] = await daily_context(
                db, trip, day, map_client=map_client, weather_client=weather_client
            )
    return contexts


async def _sunrise_context(db: AsyncSession, trip: Trip, day: TripDay) -> str:
    rise = await db.get(TripDayRiseSet, (trip.trip_id, day.day_index))
    sunrise = (
        local_time(rise.sunrise_at)
        if rise is not None
        and rise.locdate == effective_date(trip, day)
        and rise.status == "success"
        and not rise.stale
        else "정보 없음"
    )
    return f"일출: {sunrise} (KST)"


def schedule_snapshot(
    trips: list[Trip], *, today: date, day: TripDay | None = None
) -> dict[str, object]:
    snapshots: dict[str, dict[str, object]] = {}
    for trip in trips:
        entry: dict[str, object] = {
            "start_date": trip.start_date.isoformat() if trip.start_date else None,
            "end_date": trip.end_date.isoformat() if trip.end_date else None,
        }
        if day is not None:
            target = effective_date(trip, day)
            entry.update(
                day_index=day.day_index, effective_date=target.isoformat() if target else None
            )
        snapshots[str(trip.trip_id)] = entry
    return {"reference_date": today.isoformat(), "trips": snapshots}


async def plan_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime,
    map_client: KorTravelMapClient | None = None,
    weather_client: KorTravelWeatherClient | None = None,
    prepared_contexts: dict[tuple[uuid.UUID, int, date], str] | None = None,
) -> int:
    pref = await preferences(db, user_id, lock=True)
    user = await db.get(User, user_id)
    if (
        pref is None
        or user is None
        or not user.is_active
        or user.deleted_at is not None
        or user.status != "active"
    ):
        return 0
    local = now.astimezone(KST)
    today = local.date()
    expires_at = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    if local.strftime("%H:%M") < pref.send_time:
        return 0
    trips = list(
        (
            await db.scalars(
                select(Trip)
                .where(Trip.owner_user_id == user_id, Trip.deleted_at.is_(None))
                .order_by(Trip.trip_id)
                .with_for_update()
            )
        ).all()
    )
    count = 0
    if pref.daily_enabled:
        for trip in trips:
            days = list(
                (
                    await db.scalars(
                        select(TripDay)
                        .where(TripDay.trip_id == trip.trip_id)
                        .order_by(TripDay.day_index)
                    )
                ).all()
            )
            for day in days:
                target_date = effective_date(trip, day)
                if target_date not in (today, today + timedelta(days=1)):
                    continue
                key = _daily_key(trip.trip_id, target_date, today)
                existing = await db.scalar(
                    select(TelegramNotification.id).where(
                        TelegramNotification.user_id == user_id,
                        TelegramNotification.occurrence_key == key,
                    )
                )
                if existing is not None:
                    continue
                targets = await linked_targets(db, trip)
                if not targets:
                    continue
                assert target_date is not None
                context = (prepared_contexts or {}).get(
                    (trip.trip_id, day.day_index, target_date), "날씨: 정보를 확인하지 못했습니다."
                )
                context += "\n" + await _sunrise_context(db, trip, day)
                await enqueue(
                    db,
                    user_id=user_id,
                    key=key,
                    category="daily_brief",
                    fingerprint=key,
                    trip_ids=[trip.trip_id],
                    message=("오늘 일정" if target_date == today else "내일 일정")
                    + "\n"
                    + await itinerary(db, trip, day.day_index)
                    + "\n\n"
                    + context,
                    recipients=[(target, link) for target, link in targets],
                    consent_generation=pref.generation,
                    schedule_snapshot=schedule_snapshot([trip], today=today, day=day),
                    expires_at=expires_at,
                )
                count += 1
    if (
        pref.weekly_enabled
        and local.weekday() == pref.weekly_day
        and pref.weekly_target_id is not None
    ):
        upcoming = [
            trip
            for trip in trips
            if trip.start_date is not None and today <= trip.start_date < today + timedelta(days=7)
        ]
        if upcoming:
            target = await db.scalar(
                select(TelegramTarget).where(
                    TelegramTarget.id == pref.weekly_target_id,
                    TelegramTarget.user_id == user_id,
                    TelegramTarget.deleted_at.is_(None),
                    TelegramTarget.is_enabled.is_(True),
                    TelegramTarget.last_verified_at.is_not(None),
                )
            )
            if target is not None:
                key = f"weekly:{today}"
                existing = await db.scalar(
                    select(TelegramNotification.id).where(
                        TelegramNotification.user_id == user_id,
                        TelegramNotification.occurrence_key == key,
                    )
                )
                if existing is None:
                    message = "🧳 앞으로 7일의 여행\n" + "\n".join(
                        f"• {summary(trip.title, 200)} · {trip.start_date} ~ {trip.end_date or '미정'}"
                        for trip in sorted(
                            upcoming,
                            key=lambda value: (value.start_date or date.max, str(value.trip_id)),
                        )
                    )
                    await enqueue(
                        db,
                        user_id=user_id,
                        key=key,
                        category="weekly_summary",
                        fingerprint=key,
                        trip_ids=[trip.trip_id for trip in upcoming],
                        message=message,
                        recipients=[(target, None)],
                        consent_generation=pref.generation,
                        schedule_snapshot=schedule_snapshot(upcoming, today=today),
                        expires_at=expires_at,
                    )
                    count += 1
    return count


# planner 단일 실행 잠금. Dagster 호출이 timeout으로 끊겨도 API 쪽 실행은 끝까지 돌므로
# 다음 tick이 겹치지 않도록 프로세스 경계를 넘는 session advisory lock으로 막는다.
_PLANNER_LOCK_NAMESPACE = 0x54474C50  # "TGLP"
_PLANNER_LOCK_RESOURCE = 0x504C414E  # "PLAN"


@asynccontextmanager
async def _single_flight() -> AsyncIterator[bool]:
    """잠금을 얻으면 True.

    잠금 연결은 요청 pool 밖의 전용 NullPool 연결이다 — 매 tick 최대 예산 동안 pool 연결 하나를
    묶어 두지 않는다. 끝에는 연결을 닫아 어떤 경로로 끝나도 잠금이 남지 않게 한다. 연결이 tick 도중
    끊기면 잠금도 풀려 다음 tick이 겹칠 수 있지만, 발생키 unique가 중복 적재를 막는다.
    """
    lock_engine = create_async_engine(
        db_session.engine.url,
        poolclass=NullPool,
        connect_args={"server_settings": SESSION_TIMEOUT_SERVER_SETTINGS},
    )
    connection = lock_engine.connect()
    started = False
    try:
        await connection.start()
        started = True
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:namespace, :resource)"),
            {"namespace": _PLANNER_LOCK_NAMESPACE, "resource": _PLANNER_LOCK_RESOURCE},
        )
        # transaction을 닫아 idle-in-transaction timeout과 무관하게 session 잠금만 유지한다.
        await connection.commit()
        yield acquired is True
    finally:

        async def discard() -> None:
            # 연결을 폐기하면 backend가 끝나며 session 잠금도 함께 풀린다(unlock 실패 경로 없음).
            try:
                if started:
                    try:
                        await connection.invalidate()
                    finally:
                        await connection.close()
            finally:
                await lock_engine.dispose()

        task = asyncio.create_task(discard())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise


async def plan_due(
    *,
    now: datetime | None = None,
    map_client: KorTravelMapClient | None = None,
    weather_client: KorTravelWeatherClient | None = None,
) -> dict[str, int]:
    """한 tick. 이전 실행이 남아 있으면 건너뛰고, 시간 예산을 넘기면 남은 사용자를 다음 tick으로 미룬다."""
    async with _single_flight() as acquired:
        if not acquired:
            return {"users": 0, "enqueued": 0, "failed": 0, "skipped": 1}
        return await _plan_users(now=now, map_client=map_client, weather_client=weather_client)


async def _plan_users(
    *,
    now: datetime | None,
    map_client: KorTravelMapClient | None,
    weather_client: KorTravelWeatherClient | None,
) -> dict[str, int]:
    current = now or datetime.now(UTC)
    started = monotonic()
    budget = settings.pinvi_telegram_planner_budget_seconds
    async with db_session.async_session_factory() as db:
        # 지난 tick에서 처리하지 못한(가장 오래 기다린) 사용자부터 처리한다.
        user_ids = list(
            (
                await db.scalars(
                    select(TelegramPreferences.user_id)
                    .where(
                        or_(
                            TelegramPreferences.weather_enabled.is_(True),
                            TelegramPreferences.daily_enabled.is_(True),
                            TelegramPreferences.weekly_enabled.is_(True),
                        )
                    )
                    .order_by(
                        TelegramPreferences.last_planned_at.asc().nulls_first(),
                        TelegramPreferences.user_id,
                    )
                )
            ).all()
        )
    enqueued = failed = processed = 0
    for user_id in user_ids:
        if processed and monotonic() - started >= budget:
            break
        processed += 1
        try:
            # 처리 전에 cursor를 옮긴다. 이 사용자가 실패해도 다음 tick은 뒤 사용자부터 시작한다.
            async with db_session.async_session_factory() as cursor_db:
                await cursor_db.execute(
                    update(TelegramPreferences)
                    .where(TelegramPreferences.user_id == user_id)
                    .values(last_planned_at=func.clock_timestamp())
                )
                await cursor_db.commit()
            weather_prepared = await prepare_weather(
                user_id,
                now=current + timedelta(seconds=monotonic() - started),
                client=weather_client,
            )
            async with db_session.async_session_factory() as weather_db:
                weather_count, weather_failed = await plan_weather(
                    weather_db,
                    user_id,
                    weather_prepared,
                    now=current + timedelta(seconds=monotonic() - started),
                )
                await weather_db.commit()
            enqueued += weather_count
            failed += weather_failed
            if weather_failed:
                PLANNING_FAILURES.labels(code="WEATHER_ALERT_CHECK_FAILED").inc(weather_failed)
            async with db_session.async_session_factory() as context_db:
                contexts = await _prepare_daily_contexts(
                    context_db,
                    user_id,
                    now=current,
                    map_client=map_client,
                    weather_client=weather_client,
                )
            async with db_session.async_session_factory() as db:
                enqueued += await plan_user(
                    db,
                    user_id,
                    now=current,
                    map_client=map_client,
                    weather_client=weather_client,
                    prepared_contexts=contexts,
                )
                await db.commit()
        except TelegramMessageTooLarge:
            # 한 사용자의 입력 제한을 다른 사용자에게 전파하지 않는다. 원문·예외·대상ID는 저장하지 않는다.
            failed += 1
            day = current.astimezone(KST).date().isoformat()
            key = f"planning_error:{day}"
            async with db_session.async_session_factory() as db:
                created = await db.scalar(
                    insert(TelegramNotification)
                    .values(
                        user_id=user_id,
                        occurrence_key=key,
                        category="planning_error",
                        request_fingerprint=key,
                        trip_ids=[],
                        chunks=[],
                        error_code=TelegramMessageTooLarge.code,
                        error_message="일정이 너무 길어 예약 알림을 만들지 못했습니다. 장소·메모를 줄이거나 일정을 나누어 주세요.",
                    )
                    .on_conflict_do_nothing(index_elements=["user_id", "occurrence_key"])
                    .returning(TelegramNotification.id)
                )
                await db.commit()
            if created is not None:
                PLANNING_FAILURES.labels(code=TelegramMessageTooLarge.code).inc()
        except Exception as exc:
            # 한 사용자의 예상 밖 오류가 user_id 뒤 순서의 모든 예약을 매분 멈추지 않게 한다.
            # 이 사용자의 미커밋 변경은 세션 종료로 롤백된다. 예외 원문은 사용자 데이터를 담을 수
            # 있으므로 고정 label과 예외 형식 이름만 남긴다.
            failed += 1
            PLANNING_FAILURES.labels(code="PLANNING_UNEXPECTED").inc()
            frames = traceback.extract_tb(exc.__traceback__)[-5:]
            logger.warning(
                "telegram planning failed for user %s: %s at %s",
                user_id,
                type(exc).__name__,
                " <- ".join(
                    f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno}" for f in reversed(frames)
                ),
            )
    return {
        "users": len(user_ids),
        "enqueued": enqueued,
        "failed": failed,
        "processed": processed,
        "deferred": len(user_ids) - processed,
    }
