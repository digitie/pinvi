"""일정 요약과 Telegram 길이 제한. 외부 콘텐츠를 markup으로 해석하지 않는다."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay

KST = ZoneInfo("Asia/Seoul")


def local_time(value: datetime | None) -> str:
    return value.astimezone(KST).strftime("%H:%M") if value else "미정"


def summary(value: str | None, limit: int = 480) -> str:
    clean = " ".join((value or "").split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def effective_date(trip: Trip, day: TripDay) -> date | None:
    return day.date or (
        trip.start_date + timedelta(days=day.day_index - 1) if trip.start_date else None
    )


def itinerary_text(trip: Trip, days: list[TripDay], pois: list[TripDayPoi]) -> str:
    lines = [f"🧳 {trip.title}", "시간: 한국 표준시(KST)"]
    for day in days:
        effective = effective_date(trip, day)
        lines.extend(
            [
                "",
                f"{day.day_index}일차 · {effective.isoformat() if effective else '날짜 미정'}"
                + (f" · {day.title}" if day.title else ""),
            ]
        )
        if day.note:
            lines.append(f"일자 메모: {summary(day.note)}")
        selected = [poi for poi in pois if poi.day_index == day.day_index]
        if not selected:
            lines.append("등록된 장소 없음")
        for poi in selected:
            name = (
                poi.feature_snapshot.get("name")
                or poi.feature_snapshot.get("title")
                or "이름 없는 장소"
            )
            lines.append(
                f"• {summary(str(name), 200)} · 도착 {local_time(poi.planned_arrival_at)} / 출발 {local_time(poi.planned_departure_at)}"
            )
            if poi.user_note:
                lines.append(f"  메모: {summary(poi.user_note)}")
    return "\n".join(lines)


def split_message(value: str, *, max_units: int = 3500) -> list[str]:
    """UTF-16 상한으로 분할한다. 전송은 plain text; 4096보다 여유를 둔다."""
    if max_units < 2:
        raise ValueError("max_units must be at least 2")
    chunks: list[str] = []
    current: list[str] = []
    units = 0
    for char in value:
        cost = 2 if ord(char) > 0xFFFF else 1
        if units + cost > max_units:
            chunks.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += cost
    if current:
        chunks.append("".join(current))
    return chunks or ["등록된 일정 없음"]
