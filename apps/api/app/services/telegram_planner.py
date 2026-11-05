"""KST 일간·주간 발생키 planner. Dagster는 좁은 인증 HTTP 경계만 호출한다."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_weather import create_map_weather_client
from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.core.config import settings
from app.db import session as db_session
from app.models.kasi import TripDayRiseSet
from app.models.poi import TripDayPoi
from app.models.telegram_notification import TelegramNotification, TelegramPreferences
from app.models.telegram_target import TelegramTarget
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.services.telegram_itinerary import KST, local_time, summary
from app.services.telegram_notifications import enqueue, itinerary, linked_targets, preferences
from app.services.trip_weather_batch import (
    build_trip_weather_via_kor_travel_map,
    build_trip_weather_via_kor_travel_weather,
)


def effective_date(trip: Trip, day: TripDay) -> date | None:
    return day.date or (
        trip.start_date + timedelta(days=day.day_index - 1) if trip.start_date else None
    )


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
    rise = await db.get(TripDayRiseSet, (trip.trip_id, day.day_index))
    sunrise = (
        local_time(rise.sunrise_at)
        if rise is not None
        and rise.locdate == target_date
        and rise.status == "success"
        and not rise.stale
        else "정보 없음"
    )
    cards: dict[int, dict[str, dict[str, Any]]] = {}
    # weather 해석 helper는 read connection을 해제하므로 별도 세션을 쓴다.
    # planner의 동의·Trip 잠금/원자적 enqueue transaction은 유지한다.
    async with db_session.async_session_factory() as weather_db:
        if (
            settings.pinvi_kor_travel_map_weather_enabled
            and map_client is not None
            and map_client.has_service_token
        ):
            _, cards = await build_trip_weather_via_kor_travel_map(
                weather_db,
                pois=pois,
                day_effective_date={day.day_index: target_date},
                map_client=create_map_weather_client(map_client),
                weather_client=weather_client,
                budget_seconds=8,
            )
        elif not settings.pinvi_kor_travel_map_weather_enabled and weather_client is not None:
            _, cards = await build_trip_weather_via_kor_travel_weather(
                weather_db,
                pois=pois,
                day_effective_date={day.day_index: target_date},
                weather_client=weather_client,
                budget_seconds=8,
            )
    return weather_summary(cards.get(day.day_index, {})) + f"\n일출: {sunrise} (KST)"


async def plan_user(
    db: AsyncSession,
    user_id: Any,
    *,
    now: datetime,
    map_client: KorTravelMapClient | None = None,
    weather_client: KorTravelWeatherClient | None = None,
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
                key = f"daily:{trip.trip_id}:{target_date}:{'today' if target_date == today else 'eve'}"
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
                context = await daily_context(
                    db, trip, day, map_client=map_client, weather_client=weather_client
                )
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
                    )
                    count += 1
    return count


async def plan_due(
    *,
    now: datetime | None = None,
    map_client: KorTravelMapClient | None = None,
    weather_client: KorTravelWeatherClient | None = None,
) -> dict[str, int]:
    current = now or datetime.now(UTC)
    async with db_session.async_session_factory() as db:
        user_ids = list(
            (
                await db.scalars(
                    select(TelegramPreferences.user_id)
                    .where(
                        or_(
                            TelegramPreferences.daily_enabled.is_(True),
                            TelegramPreferences.weekly_enabled.is_(True),
                        )
                    )
                    .order_by(TelegramPreferences.user_id)
                )
            ).all()
        )
    enqueued = 0
    for user_id in user_ids:
        async with db_session.async_session_factory() as db:
            enqueued += await plan_user(
                db, user_id, now=current, map_client=map_client, weather_client=weather_client
            )
            await db.commit()
    return {"users": len(user_ids), "enqueued": enqueued}
