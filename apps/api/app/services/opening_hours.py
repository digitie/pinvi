"""Map `FeatureOpeningHours`(Google Places 호환 영업시간) → 사람이 읽는 요일별 줄.

장소 영업 정보 저장(`poi_place_details`)과 지도 feature 상세 카드(`feature_detail`)가 같은 규칙을 쓴다 —
같은 영업시간이 화면마다 다르게 보이지 않게 한 곳에 둔다.

형식: `day` 0=일요일 ~ 6=토요일, `time` "HHMM", `periods[]`는 open/close 쌍, 24시간 연중무휴는 open(day=0,
"0000") 하나에 close 없음. `weekday_text`가 있으면 그대로 쓴다.
"""

from __future__ import annotations

from typing import Any

WEEKDAYS = ("일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일")
# 표시는 월요일부터.
DISPLAY_ORDER = (1, 2, 3, 4, 5, 6, 0)


def _hhmm(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 4 or not value.isdigit():
        return None
    return f"{value[:2]}:{value[2:]}"


def _period_bounds(period: Any) -> tuple[int, str, str | None] | None:
    if not isinstance(period, dict):
        return None
    opening = period.get("open")
    if not isinstance(opening, dict):
        return None
    day = opening.get("day")
    start = _hhmm(opening.get("time"))
    if not isinstance(day, int) or not 0 <= day <= 6 or start is None:
        return None
    closing = period.get("close")
    end = _hhmm(closing.get("time")) if isinstance(closing, dict) else None
    return day, start, end


def _is_always_open(periods: list[Any]) -> bool:
    """Google Places 규칙: open(day=0, 0000) + close 없음 하나 = 24시간 연중무휴."""
    if len(periods) != 1 or not isinstance(periods[0], dict):
        return False
    bounds = _period_bounds(periods[0])
    return bounds is not None and bounds[:2] == (0, "00:00") and periods[0].get("close") is None


def hours_from_structured(hours: dict[str, Any]) -> tuple[list[str], set[int] | None]:
    """`FeatureOpeningHours` → (요일별 표시 줄, 쉬는 요일 집합 또는 판단 불가 None)."""
    weekday_text = [
        line.strip()
        for line in hours.get("weekday_text") or []
        if isinstance(line, str) and line.strip()
    ]
    periods = hours.get("periods")
    periods = periods if isinstance(periods, list) else []
    if _is_always_open(periods):
        return weekday_text or ["매일 24시간 영업"], set()
    by_day: dict[int, list[str]] = {}
    for period in periods:
        bounds = _period_bounds(period)
        if bounds is None:
            continue
        day, start, end = bounds
        by_day.setdefault(day, []).append(f"{start}~{end}" if end else f"{start}~")
    closed = {day for day in range(7) if day not in by_day} if by_day else None
    if weekday_text:
        return weekday_text, closed
    lines = [
        f"{WEEKDAYS[day]}: {', '.join(by_day[day]) if day in by_day else '휴무'}"
        for day in DISPLAY_ORDER
    ]
    return (lines if by_day else []), closed


def opening_hours_text(hours: Any) -> str | None:
    """구조화 영업시간(또는 문자열) → 줄바꿈으로 이은 표시 문자열. 줄 것이 없으면 None."""
    if isinstance(hours, str):
        return hours.strip() or None
    if not isinstance(hours, dict):
        return None
    lines, _closed = hours_from_structured(hours)
    return "\n".join(lines) or None
