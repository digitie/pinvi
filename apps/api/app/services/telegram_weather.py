"""공개 Weather 발표 관측을 여행 알림으로 선택한다. 원천/회차를 추정하지 않는다."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from time import monotonic

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherContractError,
    KorTravelWeatherError,
    kor_travel_weather_call_deadline,
)
from app.clients.weather_alert_events import RegionalAlertEvents, ScopedAlertEvent
from app.db import session as db_session
from app.models.telegram_notification import (
    TelegramNotification,
    TelegramWeatherObservation,
)
from app.models.trip import Trip
from app.models.user import User
from app.services.telegram_itinerary import KST, summary
from app.services.telegram_notifications import enqueue, linked_targets, preferences

ERRORS = {
    "WEATHER_ALERT_UNAVAILABLE": "날씨 서비스에 연결하지 못해 특보를 확인하지 못했습니다. 다음 주기에 재확인합니다.",
    "WEATHER_ALERT_CONTRACT": "날씨 서비스의 응답 범위·형식을 확인하지 못해 특보 알림을 만들지 않았습니다.",
    "WEATHER_ALERT_REGION_UNKNOWN": "여행 대표 지역의 적용 구역을 확인하지 못했습니다. 대표 지역을 확인하세요.",
    "WEATHER_ALERT_STALE": "특보 수집의 최신 성공을 확인하지 못했습니다. 빈 결과를 해제로 처리하지 않습니다.",
    "WEATHER_ALERT_INCOMPLETE": "특보 조회가 불완전하여 알림을 만들지 않았습니다. 다음 주기에 재확인합니다.",
    "WEATHER_ALERT_AMBIGUOUS": "같은 공식 발표의 상충 관측이 있어 알림을 만들지 않았습니다.",
}
ACTIONS = {
    "issued": "발령 발표",
    "released": "해제 발표",
    "extended": "연장 발표",
    "corrected": "정정 발표",
    "changed_issue": "변경 발령 발표",
    "changed_release": "변경 해제 발표",
    "cancelled": "발표 취소",
}


@dataclass(frozen=True)
class PreparedWeather:
    trip_id: uuid.UUID
    trip_version: int
    bjd_code: str | None
    consent_generation: uuid.UUID
    data: RegionalAlertEvents | None
    error: str | None = None


async def prepare_weather(
    user_id: uuid.UUID, *, now: datetime, client: KorTravelWeatherClient | None
) -> list[PreparedWeather]:
    """읽기 세션을 닫고 외부 HTTP를 호출한다. 모든 지역 조회에 합계8초 예산."""
    async with db_session.async_session_factory() as db:
        pref = await preferences(db, user_id)
        if pref is None or not pref.weather_enabled or pref.weather_enabled_at is None:
            return []
        user = await db.get(User, user_id)
        if user is None or not user.is_active or user.deleted_at or user.status != "active":
            return []
        today = now.astimezone(KST).date()
        rows = list(
            (
                await db.scalars(
                    select(Trip)
                    .where(
                        Trip.owner_user_id == user_id,
                        Trip.deleted_at.is_(None),
                        Trip.start_date <= today,
                        Trip.end_date >= today,
                    )
                    .order_by(Trip.trip_id)
                )
            ).all()
        )
        inputs = [(t.trip_id, t.version, t.primary_region_code) for t in rows]
        generation = pref.generation
    results: dict[str, tuple[RegionalAlertEvents | None, str | None]] = {}
    prepared: list[PreparedWeather] = []
    deadline = asyncio.get_running_loop().time() + 8
    for trip_id, version, code in inputs:
        data = None
        error = None
        if code is None or not re.fullmatch(r"(?:[0-9]{2}|[0-9]{5}|[0-9]{10})", code):
            error = "WEATHER_ALERT_REGION_UNKNOWN"
        elif client is None:
            error = "WEATHER_ALERT_UNAVAILABLE"
        else:
            if code not in results:
                try:
                    with kor_travel_weather_call_deadline(deadline):
                        async with asyncio.timeout_at(deadline):
                            data = await client.alert_events(
                                bjd_code=code, since=now - timedelta(hours=1)
                            )
                    results[code] = (data, None)
                except KorTravelWeatherContractError:
                    results[code] = (None, "WEATHER_ALERT_CONTRACT")
                except (KorTravelWeatherError, TimeoutError, ValueError):
                    results[code] = (None, "WEATHER_ALERT_UNAVAILABLE")
            data, error = results[code]
        prepared.append(PreparedWeather(trip_id, version, code, generation, data, error))
    return prepared


def response_error(data: RegionalAlertEvents, *, now: datetime) -> str | None:
    if data.region_status != "known":
        return "WEATHER_ALERT_REGION_UNKNOWN"
    if not data.events_complete:
        return "WEATHER_ALERT_INCOMPLETE"
    if (
        not data.fresh
        or data.collection_status != "success"
        or data.last_success_at is None
        or data.last_success_at > now
        or now - data.last_success_at > timedelta(minutes=15)
    ):
        return "WEATHER_ALERT_STALE"
    return None


def _matches_region(code: str, prefixes: list[str]) -> bool:
    # zero-padding 집계는 owner와 같은 명시적 BJD aggregate다.
    if len(code) == 10:
        if code[2:] == "0" * 8:
            code = code[:2]
        elif code[5:] == "0" * 5:
            code = code[:5]
    return any(
        re.fullmatch(r"(?:[0-9]{2}|[0-9]{5})", prefix)
        and (code.startswith(prefix) or prefix.startswith(code))
        for prefix in prefixes
    )


async def _failure(
    db: AsyncSession, user_id: uuid.UUID, trip_id: uuid.UUID, code: str, *, now: datetime
) -> int:
    assert code in ERRORS
    key = f"weather_error:{trip_id}:{code}:{now.astimezone(KST):%Y%m%d%H}"
    created = await db.scalar(
        insert(TelegramNotification)
        .values(
            user_id=user_id,
            occurrence_key=key,
            category="weather_alert_error",
            request_fingerprint=hashlib.sha256(key.encode()).hexdigest(),
            trip_ids=[str(trip_id)],
            chunks=[],
            error_code=code,
            error_message=ERRORS[code] + f" ({code})",
        )
        .on_conflict_do_nothing(index_elements=["user_id", "occurrence_key"])
        .returning(TelegramNotification.id)
    )
    return int(created is not None)


async def _observe(
    db: AsyncSession, trip: Trip, events: list[ScopedAlertEvent]
) -> tuple[TelegramWeatherObservation, ScopedAlertEvent | None]:
    """Trip 잠금 아래 취소 tombstone·모호성을 합친다. first_seen/hash로 revision을 추정하지 않는다."""
    announcement = events[0].announcement_id
    state = await db.get(TelegramWeatherObservation, (trip.trip_id, announcement))
    cancelled = [event for event in events if event.action == "cancelled"]
    if state is None:
        initial = cancelled[0] if cancelled else events[0]
        state = TelegramWeatherObservation(
            trip_id=trip.trip_id,
            announcement_id=announcement,
            event_id=initial.event_id,
            cancelled=bool(cancelled),
            ambiguous=len({e.event_id for e in events}) > 1,
            generation=uuid.uuid4(),
        )
        db.add(state)
    elif cancelled and not state.cancelled:
        state.event_id = cancelled[0].event_id
        state.cancelled = True
        state.generation = uuid.uuid4()
    elif not state.cancelled and any(event.event_id != state.event_id for event in events):
        if not state.ambiguous:
            state.ambiguous = True
            state.generation = uuid.uuid4()
    await db.flush()
    if state.ambiguous and not state.cancelled:
        return state, None
    chosen = next((e for e in events if e.event_id == state.event_id), None)
    if chosen is not None and state.cancelled and chosen.action != "cancelled":
        return state, None
    return state, chosen


def alert_message(trip: Trip, event: ScopedAlertEvent) -> str:
    def stamp(value: datetime | None) -> str:
        return value.astimezone(KST).strftime("%m/%d %H:%M") + " KST" if value else "미확인"

    return (
        f"🌦 {summary(trip.title, 160)} · 기상 특보 {ACTIONS[event.action]}\n"
        f"{summary(event.area_name, 200)} · {summary(event.warning_name or '특보', 50)} "
        f"{summary(event.stress_name or '', 50)}\n"
        f"공식 발표: {stamp(event.issued_at)}\n"
        f"발효: {stamp(event.starts_at)} / 종료: {stamp(event.ends_at or event.all_ends_at)}\n"
        "대표 지역과 겹치는 검증 구역의 발표 관측입니다. 일부 구역은 미확인입니다. "
        "현재 활성 상태·전체 해제·안전을 보장하지 않습니다."
    )


async def plan_weather(
    db: AsyncSession, user_id: uuid.UUID, prepared: list[PreparedWeather], *, now: datetime
) -> tuple[int, int]:
    started = monotonic()

    def current() -> datetime:
        return now + timedelta(seconds=monotonic() - started)

    pref = await preferences(db, user_id, lock=True)
    if pref is None or not pref.weather_enabled or pref.weather_enabled_at is None:
        return 0, 0
    user = await db.get(User, user_id, populate_existing=True)
    if user is None or not user.is_active or user.deleted_at or user.status != "active":
        return 0, 0
    count = failed = 0
    for item in sorted(prepared, key=lambda item: str(item.trip_id)):
        trip = await db.scalar(
            select(Trip)
            .where(Trip.trip_id == item.trip_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        when = current()
        if (
            trip is None
            or trip.deleted_at
            or trip.owner_user_id != user_id
            or trip.version != item.trip_version
            or trip.primary_region_code != item.bjd_code
            or pref.generation != item.consent_generation
            or trip.start_date is None
            or trip.end_date is None
            or not trip.start_date <= when.astimezone(KST).date() <= trip.end_date
        ):
            continue
        data = item.data
        groups: dict[str, list[ScopedAlertEvent]] = {}
        if data is not None and data.region_status == "known":
            for observation in data.events:
                if item.bjd_code is None or not _matches_region(
                    item.bjd_code, observation.bjd_prefixes
                ):
                    failed += await _failure(
                        db, user_id, trip.trip_id, "WEATHER_ALERT_CONTRACT", now=when
                    )
                    continue
                groups.setdefault(observation.announcement_id, []).append(observation)
        observations = [await _observe(db, trip, events) for events in groups.values()]
        error = item.error or (response_error(data, now=when) if data else None)
        if error:
            failed += await _failure(db, user_id, trip.trip_id, error, now=when)
            continue
        if data is None:
            continue
        for state, event in observations:
            if event is None:
                if state.ambiguous and not state.cancelled:
                    failed += await _failure(
                        db, user_id, trip.trip_id, "WEATHER_ALERT_AMBIGUOUS", now=when
                    )
                continue
            if (
                event.action not in ACTIONS
                or event.issued_at is None
                or not pref.weather_enabled_at <= event.issued_at <= when
                or when - event.issued_at >= timedelta(minutes=30)
                or event.first_seen_at > when
            ):
                continue
            key = (
                "weather:"
                + str(trip.trip_id)
                + ":"
                + hashlib.sha256(f"{event.announcement_id}:{event.action}".encode()).hexdigest()
            )
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
            expires = min(
                when + timedelta(minutes=15),
                event.issued_at + timedelta(minutes=30),
                datetime.combine(trip.end_date + timedelta(days=1), time.min, tzinfo=KST),
            )
            await enqueue(
                db,
                user_id=user_id,
                key=key,
                category="weather_alert",
                fingerprint=hashlib.sha256(key.encode()).hexdigest(),
                trip_ids=[trip.trip_id],
                message=alert_message(trip, event),
                recipients=[(target, link) for target, link in targets],
                consent_generation=pref.generation,
                expires_at=expires,
                schedule_snapshot={
                    "trip_version": trip.version,
                    "bjd_code": item.bjd_code,
                    "announcement_id": event.announcement_id,
                    "event_id": state.event_id,
                    "observation_generation": str(state.generation),
                },
            )
            count += 1
    return count, failed
