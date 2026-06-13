"""Telegram 알림 메시지 빌더 — `docs/integrations/telegram.md` §7. T-106.

plain text 메시지를 만든다(§1 — 일반 user 알림에 stack trace/키/토큰/로그 경로 금지).
weekly_summary/daily_brief(§7.1/7.2)는 Dagster schedule 후속 — 여기는 즉시 알림 2종.
"""

from __future__ import annotations

from datetime import date


def _format_date(value: date | None) -> str:
    if value is None:
        return "미정"
    return f"{value.month}월 {value.day}일"


def _format_range(start: date | None, end: date | None) -> str:
    return f"{_format_date(start)} ~ {_format_date(end)}"


def build_trip_created_message(
    *,
    title: str,
    start_date: date | None,
    end_date: date | None,
    region_hint: str | None,
) -> str:
    """신규 trip 생성 알림 (owner의 default target용)."""
    lines = [
        f"🧳 새 여행이 만들어졌습니다 — {title}",
        "",
        f"📅 {_format_range(start_date, end_date)}",
    ]
    if region_hint:
        lines.append(f"📍 {region_hint}")
    return "\n".join(lines)


def build_companion_invited_message(
    *,
    trip_title: str,
    display_name: str | None,
) -> str:
    """동반자 초대 알림 (초대된 기존 사용자의 default target용).

    이메일 등 PII는 넣지 않는다 — 그룹 채널일 수 있다(§9).
    """
    who = f"{display_name}님" if display_name else "회원님"
    return "\n".join(
        [
            f"✉️ {who}, 여행에 초대되었습니다 — {trip_title}",
            "",
            "Pinvi에서 일정을 확인해 보세요.",
        ]
    )
